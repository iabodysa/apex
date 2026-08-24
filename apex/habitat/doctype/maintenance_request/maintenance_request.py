# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe import _
from frappe.desk.form.assign_to import close_all_assignments
from frappe.model.document import Document
from frappe.model.mapper import get_mapped_doc
from frappe.model.workflow import apply_workflow
from frappe.utils import flt

from apex.apex_core.utils.company import resolve_company

_TRANSITION_SAVEPOINT = "maintenance_request_transition"


class MaintenanceRequest(Document):
    pass


def validate(doc, method=None):
    if doc.is_new() and not doc.reported_by:
        doc.reported_by = frappe.session.user

    if not doc.company:
        doc.company = resolve_company("Habitat")

    _validate_status_rules(doc)


def _validate_status_rules(doc):
    status = doc.status or "Open"
    if status in ("Resolved", "Closed") and not doc.resolution_notes:
        frappe.throw(_("Resolution Notes are required to resolve or close a Maintenance Request."))
    if flt(doc.cost_of_repair) < 0:
        frappe.throw(_("Cost of Repair cannot be negative."))


@frappe.whitelist(methods=["POST"])
def make_work_order(source_name, target_doc=None):
    frappe.has_permission("Maintenance Request", "read", doc=source_name, throw=True)

    def set_missing_values(source, target):
        target.maintenance_request = source.name
        target.status = "Planned"

    doclist = get_mapped_doc(
        "Maintenance Request",
        source_name,
        {
            "Maintenance Request": {
                "doctype": "Maintenance Work Order",
                "field_no_map": ["status"],
            }
        },
        target_doc,
        set_missing_values,
    )

    return doclist


def _locked_request(name: str):
    doc = frappe.get_doc("Maintenance Request", name, for_update=True)
    doc.check_permission("write")
    return doc


@frappe.whitelist(methods=["POST"])
def close_request(name: str) -> dict:
    doc = _locked_request(name)
    if doc.docstatus != 1:
        frappe.throw(_("Only submitted Maintenance Requests can be closed."))

    frappe.db.savepoint(_TRANSITION_SAVEPOINT)
    try:
        apply_workflow(doc, "Close")
        close_all_assignments("Maintenance Request", doc.name)
    except Exception:
        frappe.db.rollback(save_point=_TRANSITION_SAVEPOINT)
        raise
    return {"name": doc.name, "status": doc.status}


@frappe.whitelist(methods=["POST"])
def reopen_request(name: str, reason: str) -> dict:
    reason = str(reason or "").strip()
    if not reason:
        frappe.throw(_("A reason is required to reopen a Maintenance Request."))

    doc = _locked_request(name)
    if doc.docstatus != 1:
        frappe.throw(_("Only submitted Maintenance Requests can be reopened."))

    frappe.db.savepoint(_TRANSITION_SAVEPOINT)
    try:
        apply_workflow(doc, "Reopen")
        doc.add_comment(
            "Comment",
            _("Maintenance Request reopened: {0}").format(reason),
        )
    except Exception:
        frappe.db.rollback(save_point=_TRANSITION_SAVEPOINT)
        raise
    return {"name": doc.name, "status": doc.status}
