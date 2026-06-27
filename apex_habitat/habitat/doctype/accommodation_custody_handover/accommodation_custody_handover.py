"""Accommodation Custody Handover controller — the OTP-confirmed move of
externally-purchased goods from the procurement intake store into a receiving
accommodation supervisor's building store, via the Accommodation Stock Ledger.

Lifecycle: Draft -> (submit) Pending Receipt -> Under Review -> Approved
-> (confirm_handover with OTP) Confirmed; Rejected and Cancelled reverse the ship
leg. On submit the ship leg leaves the source store and a one-time password is
issued to the procurement supervisor; the receiving supervisor confirms receipt
with that code, which posts the receive leg into the destination store.

The two-leg ship/receive and the ledger helpers mirror Accommodation Material
Transfer; the OTP confirmation, separation of duties, and review gate live in the
custody_handover API module. Lifecycle logic lives as Document methods (not
module functions) so it runs from the class without any hooks.py doc_events
wiring. OTP generation/hashing are module functions so a regenerate from the API
re-uses the exact same mechanism."""

from __future__ import annotations

import hashlib
import secrets

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_to_date, flt, now_datetime

VOUCHER_TYPE = "Accommodation Custody Handover"


class AccommodationCustodyHandover(Document):
    def validate(self):
        if not self.items:
            frappe.throw(_("At least one item is required on a Custody Handover."))
        if self.from_building and self.to_building and self.from_building == self.to_building:
            frappe.throw(_("Source and destination buildings must be different."))
        if self.procurement_supervisor and self.receiving_supervisor and self.procurement_supervisor == self.receiving_supervisor:
            frappe.throw(_("The procurement supervisor and the receiving supervisor must be different people."))
        from apex_habitat.habitat.doctype.accommodation_stock_ledger.accommodation_stock_ledger import (
            _resolve_item,
        )
        for row in self.items:
            if (row.qty or 0) <= 0:
                frappe.throw(_("Row {0}: Qty must be greater than zero.").format(row.idx))
            if row.item_type and row.item:
                item_name, uom, _cost = _resolve_item(row.item_type, row.item)
                row.item_name = item_name
                row.uom = uom

    def on_submit(self):
        """Post the ship leg out of the source store, mark the handover Pending
        Receipt, and issue the one-time password to the procurement supervisor."""
        self._assert_source_availability()
        self._post_ship_leg()
        self.db_set("status", "Pending Receipt")
        code = generate_otp(self)
        # Surface the plaintext once so the Desk save response can show it to the
        # procurement supervisor. Only its hash is stored; the code is never persisted.
        frappe.response["handover_otp"] = code

    def on_cancel(self):
        """Reverse every ledger row this handover posted (ship and, if any, receive)."""
        from apex_habitat.habitat.doctype.accommodation_stock_ledger.accommodation_stock_ledger import (
            reverse_stock_entries,
        )
        reverse_stock_entries(VOUCHER_TYPE, self.name)
        self.db_set("status", "Cancelled")

    def _assert_source_availability(self):
        """Reject the handover if the source store cannot cover the requested
        quantity for any item (aggregated per item, in case of duplicate rows)."""
        from apex_habitat.habitat.doctype.accommodation_stock_ledger.accommodation_stock_ledger import (
            get_store_balance,
        )
        needed = {}
        for row in self.items:
            needed[(row.item_type, row.item)] = needed.get((row.item_type, row.item), 0) + flt(row.qty)
        for (item_type, item), qty in needed.items():
            # for_update: lock the source store's ledger rows before reading the
            # balance so a concurrent handover/transfer draining the same store can't
            # pass this check on a stale balance and overdraw it negative (TOCTOU).
            available = get_store_balance(item_type, item, self.from_building, for_update=True)
            if qty > available:
                frappe.throw(
                    _("Cannot hand over {0} unit(s) of {1} from {2}: only {3} available in the store.").format(
                        qty, item, self.from_building, available
                    )
                )

    def _post_ship_leg(self):
        """Stock leaves the source store (employee unset). Idempotent."""
        from apex_habitat.habitat.doctype.accommodation_stock_ledger.accommodation_stock_ledger import (
            has_stock_entries,
            post_stock_entry,
        )
        if has_stock_entries(VOUCHER_TYPE, self.name):
            return
        for row in self.items:
            post_stock_entry(
                item_type=row.item_type, item=row.item, qty=-flt(row.qty),
                building=self.from_building, employee=None,
                from_building=self.from_building, to_building=self.to_building,
                voucher_type=VOUCHER_TYPE, voucher_no=self.name, voucher_detail_no=row.name,
                posting_date=self.handover_date,
            )


def hash_otp(code: str, name: str) -> str:
    """The only place the OTP is hashed: sha256 of the code salted with the
    document name, so a hash is useless on any other handover."""
    return hashlib.sha256((code + name).encode()).hexdigest()


def generate_otp(doc) -> str:
    """Issue a fresh 6-digit code: store ONLY its hash and an expiry window, reset
    the attempt counter and any lockout, and return the plaintext ONCE. The
    validity window falls back to 10 minutes when the setting is unset (a new Int
    field on the Habitat Settings Single reads 0, not its DocType default)."""
    code = f"{secrets.randbelow(1_000_000):06d}"
    validity = frappe.db.get_single_value("Habitat Settings", "handover_otp_validity_minutes") or 10
    doc.db_set({
        "otp_hash": hash_otp(code, doc.name),
        "otp_expires_at": add_to_date(now_datetime(), minutes=int(validity)),
        "otp_attempts": 0,
        "otp_locked_until": None,
    })
    return code
