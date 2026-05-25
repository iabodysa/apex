from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


class IdleResidentReport(Document):
    pass


def validate(doc, method=None):
    if not doc.reported_by:
        doc.reported_by = frappe.session.user

    _validate_status_transition(doc)


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
