# Copyright (c) 2026, AFMCO and contributors
"""Facility Asset Delivery controller (T-673) — delivers a tracked Facility Asset
from a procurement intake store to an accommodation, gated behind a 3-exit
transfer lock and an on-site code receipt.

This is the ASSET-level analogue of Custody Handover (which code-receipts stock
*quantities* through the Accommodation Stock Ledger). A Facility Asset is a
serialized, individually tracked record, so the "move" is an in-place location
update on the asset plus an immutable Facility Asset Movement Ledger row — the
same engine Facility Asset Movement uses — NOT a stock-quantity post.

Lifecycle (guarded controller state machine, mirroring Custody Handover):
  Draft
   -> (submit)            Pending Exits   [on-site code issued to initiator]
   -> exit 1 (security)   Pending Exits
   -> exit 2 (logistics)  Pending Exits
   -> exit 3 (receiving)  Released        [all 3 exits passed; lock open]
   -> (confirm on-site code, by the receiving side, NOT the initiator)
                          Delivered       [asset location/custody actually moves]
  cancel -> Cancelled (reverses the movement ledger if the asset already moved).

THE 3-EXIT TRANSFER LOCK: the asset is NOT released and does NOT move until all
three exit checkpoints are passed, each by a DISTINCT role (owner-confirmable
default — see the module README / report):
  exit 1  Security / Gate       Resident Supervisor (source gate-out)
  exit 2  Logistics / Dispatch  Accommodation Manager (transit authorization)
  exit 3  Receiving Acceptance  receiving supervisor OR Procurement Supervisor
The exits MUST be cleared in order (1 -> 2 -> 3); clearing exit 3 opens the lock
(status -> Released) and issues the on-site code.

Lifecycle logic lives as Document methods so Frappe runs it natively with no
hooks.py doc_events wiring (the Goods Receipt / Custody Handover convention). The
exit-clearing + on-site confirm whitelisted APIs live in the
habitat.api.facility_asset_delivery module. OTP generation/hashing are REUSED
from custody_handover (DRY) — there is one on-site-code mechanism in the app."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import today

# The on-site code mechanism is shared with Custody Handover — one implementation.
from apex.habitat.doctype.custody_handover.custody_handover import (
    generate_otp,
)
from apex.habitat.asset_movement_engine import (
    post_asset_movement,
    reverse_asset_movement,
)

DELIVERY_DOCTYPE = "Facility Asset Delivery"
# A pseudo source_doctype for the movement ledger so a delivery-driven move is
# distinguishable from a Facility Asset Movement-driven one (both use the same
# immutable ledger).
LEDGER_SOURCE = "Facility Asset Delivery"


class FacilityAssetDelivery(Document):
    def validate(self):
        if not self.facility_asset:
            frappe.throw(_("A Facility Asset is required on a delivery."))
        if self.from_building and self.to_building and self.from_building == self.to_building:
            frappe.throw(_("Source and destination buildings must be different."))
        if (
            self.initiated_by
            and self.receiving_supervisor
            and self.initiated_by == self.receiving_supervisor
        ):
            frappe.throw(
                _("The initiator and the receiving supervisor must be different people.")
            )
        self._reconcile_origin()

    def _reconcile_origin(self):
        """Default a blank from_building from the asset's current location, and
        reject a hand-entered origin that contradicts where the asset actually is
        — so the delivery can't start from a phantom location (the same guard
        Facility Asset Movement applies)."""
        asset_building = frappe.db.get_value("Facility Asset", self.facility_asset, "building")
        if not asset_building:
            return
        if not self.from_building:
            self.from_building = asset_building
        elif self.from_building != asset_building:
            frappe.throw(
                _("From Building does not match the asset's current location ({0}).").format(
                    asset_building
                )
            )

    def on_submit(self):
        """Open the 3-exit lock (status Pending Exits) and issue the on-site code
        to the initiator. The asset does NOT move yet — it moves only when all
        three exits pass (Released) and the receiving side confirms the code."""
        self.db_set("status", "Pending Exits")
        code = generate_otp(self)
        # Surface the plaintext once so the Desk save response can show it to the
        # initiator. Only its hash is stored; the code is never persisted.
        frappe.response["delivery_otp"] = code

    def on_cancel(self):
        """Reverse the movement ledger if the asset already moved (Delivered), then
        mark Cancelled. A delivery cancelled before Delivered never moved the asset,
        so the reversal is a no-op there (idempotent)."""
        if self.status == "Delivered":
            reverse_asset_movement(LEDGER_SOURCE, self.name)
            # Revert the asset's location to where it came from.
            if frappe.db.exists("Facility Asset", self.facility_asset):
                count = frappe.db.get_value("Facility Asset", self.facility_asset, "movement_count") or 0
                frappe.db.set_value(
                    "Facility Asset",
                    self.facility_asset,
                    {
                        "building": self.from_building,
                        "movement_count": max(0, count - 1),
                    },
                )
        self.db_set("status", "Cancelled")

    def before_cancel(self):
        if not self.cancellation_reason:
            frappe.throw(_("Cancellation Reason is required before cancelling a delivery."))


def move_asset_on_delivery(doc) -> None:
    """Actually move the tracked asset into the destination on a confirmed receipt.

    Posts the immutable Facility Asset Movement Ledger row (the same engine
    Facility Asset Movement uses) and updates the asset's current location +
    previous_* audit fields in place. Idempotent: the ledger engine skips a source
    already ledgered, and the in-place update is guarded by the Delivered-status
    short-circuit in the confirm API."""
    asset = frappe.db.get_value(
        "Facility Asset",
        doc.facility_asset,
        ["building", "location_in_building", "movement_count"],
        as_dict=True,
    )
    if not asset:
        return
    company = frappe.db.get_value("Building", doc.to_building, "company")
    # Reuse the movement-ledger engine via a lightweight shim object: it reads
    # from_/to_/facility_asset/name/doctype off the passed doc. Build a thin
    # namespace matching what post_asset_movement expects.
    ledger_doc = frappe._dict(
        doctype=LEDGER_SOURCE,
        name=doc.name,
        facility_asset=doc.facility_asset,
        from_building=doc.from_building,
        from_room=None,
        to_building=doc.to_building,
        to_room=doc.to_location_in_building,
        from_company=company,
        to_company=company,
    )
    post_asset_movement(ledger_doc)
    frappe.db.set_value(
        "Facility Asset",
        doc.facility_asset,
        {
            "previous_building": asset.building,
            "previous_location_in_building": asset.location_in_building,
            "building": doc.to_building,
            "location_in_building": doc.to_location_in_building or asset.location_in_building,
            "movement_count": (asset.movement_count or 0) + 1,
            "last_movement_date": today(),
        },
    )
