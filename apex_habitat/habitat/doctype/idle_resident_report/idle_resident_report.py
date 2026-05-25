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


# Responsible department -> the role that owns it. Used to route accountability.
_DEPARTMENT_ROLE = {
    "HR": "HR Manager",
    "Operations": "Accommodation Manager",
    "Legal": "System Manager",
}


def after_insert(doc, method=None):
    """Force accountability: put the new report in the responsible department's
    desk queue as ToDos (one per active role holder) and stamp _assign. Idempotent
    — never duplicates an open ToDo for the same user."""
    role = _DEPARTMENT_ROLE.get(doc.responsible_department)
    if not role:
        return
    holders = frappe.get_all("Has Role", filters={"role": role, "parenttype": "User"}, pluck="parent")
    assignees = []
    for user in holders:
        if user in ("Administrator", "Guest"):
            continue
        if not frappe.db.get_value("User", user, "enabled"):
            continue
        if frappe.db.exists("ToDo", {"reference_type": doc.doctype, "reference_name": doc.name,
                                     "allocated_to": user, "status": "Open"}):
            continue
        frappe.get_doc({
            "doctype": "ToDo",
            "allocated_to": user,
            "reference_type": doc.doctype,
            "reference_name": doc.name,
            "description": _("Idle resident reported to {0}: employee {1} (building {2}). Please action.").format(
                doc.responsible_department, doc.employee_name or doc.employee, doc.building),
            "priority": "High" if doc.reason_category == "Legal Case" else "Medium",
            "assigned_by": frappe.session.user,
        }).insert(ignore_permissions=True)  # audit-ok
        assignees.append(user)
    if assignees:
        frappe.db.set_value(doc.doctype, doc.name, "_assign", frappe.as_json(assignees),
                            update_modified=False)


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
