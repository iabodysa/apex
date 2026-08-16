# Copyright (c) 2026, afmcoltd
from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from apex.apex_core.utils.party_link import sync_party_employee
from apex.apex_core.utils.role_assignment import assign_role


class IdleResidentReport(Document):
    pass


def validate(doc, method=None):
    """Syncs the linked employee, defaults reported_by, and enforces the status transition rules."""
    sync_party_employee(doc, require_party=True)

    if not doc.reported_by:
        doc.reported_by = frappe.session.user

    _validate_status_transition(doc)


_DEPARTMENT_ROLE = {
    "HR": "HR Manager",
    "Operations": "Accommodation Manager",
    "Legal": "System Manager",
}


def after_insert(doc, method=None):
    """Force accountability: put the new report in the responsible department's
    desk queue as ToDos (one per active role holder who may already read it).

    Routed through ``assign_role`` rather than a raw ``get_users_with_role`` +
    ``assign_to.add``: a role holder who cannot read this document would otherwise be
    handed one via a DocShare, or blocked outright with Document Sharing off
    (assign_to.py:98-110). No DocPerm currently grants HR Manager read here, so an HR
    report is queued to nobody until that is granted — reported, not silently widened.
    """
    role = _DEPARTMENT_ROLE.get(doc.responsible_department)
    if not role:
        return
    assign_role(
        doc.doctype,
        doc.name,
        role,
        _("Idle resident reported to {0}: employee {1} (building {2}). Please action.").format(
            doc.responsible_department, doc.employee_name or doc.employee, doc.building
        ),
        priority="High" if doc.reason_category == "Legal Case" else "Medium",
    )


def _validate_status_transition(doc):
    """Enforce role-based state transition rules without a full Frappe Workflow.

    Stamps acknowledge/resolve audit fields and prevents more than one active
    (Open/Acknowledged) report from existing for the same employee.
    """
    status = doc.status or "Open"

    if status == "Resolved":
        if not doc.resolution_notes:
            frappe.throw(_("Resolution Notes are required when resolving an Idle Resident Report."))
        if not doc.resolved_by:
            doc.resolved_by = frappe.session.user
        if not doc.resolved_on:
            doc.resolved_on = frappe.utils.today()

    if status == "Acknowledged":
        if not doc.acknowledged_by:
            doc.acknowledged_by = frappe.session.user
        if not doc.acknowledged_on:
            doc.acknowledged_on = frappe.utils.today()

    if doc.is_new() and doc.employee:
        existing = frappe.get_all(
            "Idle Resident Report",
            filters={
                "employee": doc.employee,
                "status": ["in", ["Open", "Acknowledged"]],
            },
            pluck="name",
            limit=1,
        )
        if existing:
            frappe.throw(
                _("An open Idle Resident Report already exists for employee {0}: {1}.").format(
                    doc.employee, existing[0]
                )
            )
