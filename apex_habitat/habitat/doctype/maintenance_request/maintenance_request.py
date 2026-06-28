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
    """Create a Maintenance Work Order from this request.

    field_map is intentionally omitted for building/issue_type: get_mapped_doc
    copies same-named fields automatically (mapper lines 190-195).  status is
    excluded via field_no_map so the source "Open" value is never copied; the
    correct "Planned" value is written by set_missing_values instead.

    Fields on Maintenance Request that have NO matching fieldname on Maintenance
    Work Order (room, bed, priority) are therefore never referenced here, which
    prevents the silent-drop data-loss described in P-082.
    """
    frappe.has_permission("Maintenance Request", "read", doc=source_name, throw=True)
    from frappe.model.mapper import get_mapped_doc

    def set_missing_values(source, target):
        target.maintenance_request = source.name
        target.status = "Planned"

    doclist = get_mapped_doc(
        "Maintenance Request",
        source_name,
        {
            "Maintenance Request": {
                "doctype": "Maintenance Work Order",
                # building and issue_type are copied automatically (same fieldname
                # on both sides); no explicit field_map entry needed.
                # status is excluded so the source "Open" does not bleed through.
                "field_no_map": ["status"],
            }
        },
        target_doc,
        set_missing_values,
    )

    return doclist
