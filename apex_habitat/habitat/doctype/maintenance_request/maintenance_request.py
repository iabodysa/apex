"""Maintenance Request controller."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class MaintenanceRequest(Document):
    pass


def before_save(doc, method=None):
    # [#51y4un]
    if doc.is_new() and not doc.reported_by:
        doc.reported_by = frappe.session.user

    if not doc.company:
        from apex_habitat.apex_core.doctype.habitat_settings.habitat_settings import (
            get_default_company,
        )
        doc.company = get_default_company()

    _validate_status_rules(doc)


def _validate_status_rules(doc):
    status = doc.status or "Open"
    if status == "Assigned" and not doc.assigned_to:
        frappe.throw(_("Assigned To is required when status is Assigned."))
    if status in ("Resolved", "Closed") and not doc.resolution_notes:
        frappe.throw(_("Resolution Notes are required to resolve or close a Maintenance Request."))
    # A repair cost is a spend; a negative value is never valid.
    if flt(doc.cost_of_repair) < 0:
        frappe.throw(_("Cost of Repair cannot be negative."))


@frappe.whitelist(methods=["POST"])
def make_work_order(source_name, target_doc=None):
    frappe.has_permission("Maintenance Request", "read", doc=source_name, throw=True)
    from frappe.model.mapper import get_mapped_doc

    def set_missing_values(source, target):
        target.maintenance_request = source.name
        target.status = "Planned"

    doclist = get_mapped_doc("Maintenance Request", source_name, {
        "Maintenance Request": {
            "doctype": "Maintenance Work Order",
            "field_map": {
                "building": "building",
                "issue_type": "issue_type"
            }
        }
    }, target_doc, set_missing_values)

    return doclist
