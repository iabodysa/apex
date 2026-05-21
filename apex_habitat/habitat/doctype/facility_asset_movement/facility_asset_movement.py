"""Facility Asset Movement controller."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


class FacilityAssetMovement(Document):
    def before_save(self):
        # Validate document properties
        if self.doctype != "Facility Asset Movement":
            frappe.throw("DocType mismatch")


def validate(doc, method=None):
    if doc.from_building == doc.to_building and doc.from_room == doc.to_room:
        frappe.throw(_("From and To location must differ for a Facility Asset Movement."))


def on_submit(doc, method=None):
    if frappe.db.exists("DocType", "Facility Asset"):
        asset_fields = {f.fieldname for f in frappe.get_meta("Facility Asset").fields}
        updates = {}
        if "current_building" in asset_fields:
            updates["current_building"] = doc.to_building
        if "current_room" in asset_fields:
            updates["current_room"] = doc.to_room
        if updates:
            frappe.db.set_value("Facility Asset", doc.facility_asset, updates)


def before_cancel(doc, method=None):
    if not doc.cancellation_reason:
        frappe.throw(_("Cancellation Reason is required before cancelling a Facility Asset Movement."))
