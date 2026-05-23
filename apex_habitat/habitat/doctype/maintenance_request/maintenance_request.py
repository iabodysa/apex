"""Maintenance Request controller."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


class MaintenanceRequest(Document):
    def before_save(self):
        if not self.company:
            from apex_habitat.habitat.doctype.habitat_settings.habitat_settings import get_default_company
            self.company = get_default_company()

        self._validate_status_rules()

    def _validate_status_rules(self):
        status = self.status or "Open"
        if status == "Assigned" and not self.assigned_to:
            frappe.throw(_("Assigned To is required when status is Assigned."))
        if status in ("Resolved", "Closed") and not self.resolution_notes:
            frappe.throw(_("Resolution Notes are required to resolve or close a Maintenance Request."))

@frappe.whitelist()
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
