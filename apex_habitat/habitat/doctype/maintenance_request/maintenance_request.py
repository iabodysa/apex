"""Maintenance Request controller."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


class MaintenanceRequest(Document):
    pass


def before_save(doc, method=None):
    # Stamp the creator server-side on new tickets so a non-privileged 'All'
    # creator cannot spoof ownership and the owner-scoping permission hook has a
    # trustworthy reported_by. reported_by is reqd=1, so defaulting it here (runs
    # before mandatory validation) also lets a plain user POST via REST without
    # supplying it. Idempotent: only fires on a new record with reported_by unset.
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
