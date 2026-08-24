# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.desk.form import assign_to as _assign_to
from frappe.desk.form.assign_to import close_all_assignments
from frappe.utils.user import get_users_with_role

ASSIGNMENT_STATUSES = ("Open", "Overdue")


def role_holders(role: str) -> list[str]:
    return [user for user in get_users_with_role(role) if user != "Guest"]


def role_holders_escalating(*roles: str) -> list[str]:
    for role in roles:
        holders = role_holders(role)
        if holders:
            return holders
    return []


def assign_role(doctype: str, name: str, role: str, description: str, priority: str = "Medium") -> int:
    doc = frappe.get_doc(doctype, name)
    assignees = [
        user for user in role_holders(role) if frappe.has_permission(doc=doc, user=user)
    ]
    if not assignees:
        return 0
    _assign_to.add(
        {
            "doctype": doctype,
            "name": name,
            "assign_to": assignees,
            "description": description,
            "priority": priority,
            "assigned_by": frappe.session.user,
        }
    )
    return len(assignees)


def clear_assignment(doctype: str, name: str) -> int:
    todos = frappe.get_all(
        "ToDo",
        filters={
            "reference_type": doctype,
            "reference_name": name,
            "status": ["in", ASSIGNMENT_STATUSES],
        },
        pluck="name",
    )
    if todos:
        close_all_assignments(doctype, name)
    return len(todos)


def reconcile_role_queue(doctype: str, still_needing_attention) -> int:
    keep = set(still_needing_attention)
    cleared = 0
    for name in frappe.get_all(
        "ToDo",
        filters={
            "reference_type": doctype,
            "reference_name": ["is", "set"],
            "status": ["in", ASSIGNMENT_STATUSES],
        },
        pluck="reference_name",
        distinct=True,
    ):
        if name not in keep:
            cleared += clear_assignment(doctype, name)
    return cleared
