"""Facility Asset Movement controller."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


class FacilityAssetMovement(Document):
    pass


def before_save(doc, method=None):
    _populate_company_fields(doc)
    _detect_intercompany(doc)


def validate(doc, method=None):
    if doc.from_building == doc.to_building and doc.from_room == doc.to_room:
        frappe.throw(_("From and To location must differ for a Facility Asset Movement."))

    if doc.is_intercompany:
        _validate_intercompany_gates(doc)


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


def _populate_company_fields(doc):
    if doc.from_building and not doc.from_company:
        doc.from_company = frappe.db.get_value("Accommodation Building", doc.from_building, "company") or None
    if doc.to_building and not doc.to_company:
        doc.to_company = frappe.db.get_value("Accommodation Building", doc.to_building, "company") or None


def _detect_intercompany(doc):
    if doc.from_company and doc.to_company and doc.from_company != doc.to_company:
        doc.is_intercompany = 1
    else:
        doc.is_intercompany = 0


def _validate_intercompany_gates(doc):
    """Block intercompany submissions without release approval and receiving confirmation."""
    if not doc.release_approved_by:
        frappe.throw(_("Release Approved By is required for intercompany asset movement."))
    if not doc.receiving_confirmed_by:
        frappe.throw(_("Receiving Confirmed By is required for intercompany asset movement."))
    if doc.movement_category == "Intercompany Permanent" and not doc.accounting_acknowledged:
        frappe.throw(
            _("Accounting Acknowledged is required before submitting a permanent intercompany transfer.")
        )
