# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import today

from apex.habitat.asset_movement_engine import (
    ensure_asset_still_at,
    ledgered_origin,
    post_asset_movement,
    restore_asset_audit_trail,
    reverse_asset_movement,
)

DELIVERY_DOCTYPE = "Facility Asset Delivery"

LEDGER_SOURCE = "Facility Asset Delivery"


class FacilityAssetDelivery(Document):
    def validate(self):
        self._reconcile_origin()
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

    def _reconcile_origin(self):
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
        self.db_set("status", "Pending Exits")

    def on_cancel(self):
        if self.status == "Delivered":
            origin = ledgered_origin(LEDGER_SOURCE, self.name)
            reverse_asset_movement(LEDGER_SOURCE, self.name)
            if frappe.db.exists("Facility Asset", self.facility_asset):
                count = frappe.db.get_value("Facility Asset", self.facility_asset, "movement_count") or 0
                restored = {
                    "building": self.from_building,
                    "movement_count": max(0, count - 1),
                }
                if origin:
                    restored["location_in_building"] = origin.from_location
                frappe.db.set_value("Facility Asset", self.facility_asset, restored)
                restore_asset_audit_trail(self.facility_asset)
        self.db_set("status", "Cancelled")

    def before_cancel(self):
        if not self.cancellation_reason:
            frappe.throw(_("Cancellation Reason is required before cancelling a delivery."))
        if self.status == "Delivered":
            expected = {"building": self.to_building}
            if self.to_location_in_building:
                expected["location_in_building"] = self.to_location_in_building
            ensure_asset_still_at(self.facility_asset, **expected)


def move_asset_on_delivery(doc) -> None:
    asset = frappe.db.get_value(
        "Facility Asset",
        doc.facility_asset,
        ["building", "location_in_building", "movement_count"],
        as_dict=True,
    )
    if not asset:
        return
    company = frappe.db.get_value("Building", doc.to_building, "company")
    ledger_doc = frappe._dict(
        doctype=LEDGER_SOURCE,
        name=doc.name,
        facility_asset=doc.facility_asset,
        from_building=doc.from_building,
        from_room=asset.location_in_building,
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
