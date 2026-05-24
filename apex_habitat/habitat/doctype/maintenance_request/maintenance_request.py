"""Maintenance Request controller."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


class MaintenanceRequest(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from apex_habitat.habitat.doctype.maintenance_procurement_item.maintenance_procurement_item import MaintenanceProcurementItem
        from frappe.types import DF

        amended_from: DF.Link | None
        assigned_to: DF.Link | None
        bed: DF.Link | None
        building: DF.Link
        company: DF.Link | None
        cost_center: DF.Link | None
        cost_of_repair: DF.Currency
        is_logged_to_asset_history: DF.Check
        issue_description: DF.SmallText
        issue_type: DF.Literal["Electrical", "Plumbing", "Furniture", "Air Conditioning", "Fire Safety", "Pest Control", "Structural", "Other"]
        naming_series: DF.Literal["MAINT-.YYYY.-.#####"]
        priority: DF.Literal["Low", "Medium", "High", "Critical"]
        procurement_items: DF.Table[MaintenanceProcurementItem]
        related_facility_asset: DF.Link | None
        reported_by: DF.Link
        requires_procurement: DF.Check
        resolution_notes: DF.SmallText | None
        room: DF.Link
        source_inspection: DF.Link | None
        status: DF.Literal["Open", "Assigned", "In Progress", "Resolved", "Closed", "Reopened"]
        subcontractor_dispatched: DF.Link | None
        target_asset: DF.Link | None
        target_asset_category: DF.Data | None
        target_asset_location: DF.Data | None
        target_asset_name: DF.Data | None
    # end: auto-generated types
    pass


def before_save(doc, method=None):
    if not doc.company:
        from apex_habitat.habitat.doctype.habitat_settings.habitat_settings import get_default_company
        doc.company = get_default_company()

    _validate_status_rules(doc)


def _validate_status_rules(doc):
    status = doc.status or "Open"
    if status == "Assigned" and not doc.assigned_to:
        frappe.throw(_("Assigned To is required when status is Assigned."))
    if status in ("Resolved", "Closed") and not doc.resolution_notes:
        frappe.throw(_("Resolution Notes are required to resolve or close a Maintenance Request."))


@frappe.whitelist(methods=["POST"])
def make_work_order(source_name, target_doc=None):
    from frappe.model.mapper import get_mapped_doc

    def set_missing_values(source, target):
        target.maintenance_request = source.name
        target.status = "Planned"

    doclist = get_mapped_doc("Maintenance Request", source_name, {
        "Maintenance Request": {
            "doctype": "Maintenance Work Order",
            "field_map": {
                "name": "maintenance_request",
                "building": "building",
                "room": "room",
                "bed": "bed",
                "issue_type": "issue_type",
                "priority": "priority"
            }
        }
    }, target_doc, set_missing_values)

    return doclist
