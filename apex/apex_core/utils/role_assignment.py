# Copyright (c) 2026, afmcoltd
"""Put a document in a role's desk queue, and take it back out when it is settled.

Frappe already owns this: an assignment IS a ToDo, ``_assign`` on the document is
maintained by ToDo's own handlers, and the desk renders the queue, the sidebar count and
the notification without anything written here. A scheduled job that inserts its own
alert row instead builds a second inbox the user has to learn — and, the part that
actually hurt, one that nothing ever empties.

What follows from that is :func:`reconcile_role_queue`'s contract: the caller passes the
documents that still need attention FOR ANY REASON, not the ones its own pass flagged.
A document is queued while any condition holds and settled only when none does.
"""

from __future__ import annotations

import frappe
from frappe.utils.user import get_users_with_role

ASSIGNMENT_STATUSES = ("Open", "Overdue")


def role_holders(role: str) -> list[str]:
    """Enabled holders of ``role``, without Administrator or Guest.

    ``get_users_with_role`` resolves this in one join and already drops disabled users
    and the Administrator; Guest is dropped here because a role granted to Guest would
    otherwise queue work for nobody.
    """
    return [user for user in get_users_with_role(role) if user != "Guest"]


def assign_role(doctype: str, name: str, role: str, description: str, priority: str = "Medium") -> int:
    """Assign one document to every holder of ``role``. Returns how many were assigned.

    Idempotent by the framework's own rule: a holder who already has an open ToDo for
    this document is skipped, so a daily job never stacks a second copy.
    """
    from frappe.desk.form import assign_to as _assign_to

    assignees = role_holders(role)
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


def open_assignments(doctype: str) -> list[str]:
    """The documents of ``doctype`` that currently carry an open assignment."""
    return frappe.get_all(
        "ToDo",
        filters={
            "reference_type": doctype,
            "reference_name": ["is", "set"],
            "status": ["in", ASSIGNMENT_STATUSES],
        },
        pluck="reference_name",
        distinct=True,
    )


def clear_assignment(doctype: str, name: str) -> int:
    """Close every open ToDo on one document. Returns how many were closed.

    ``assign_to.remove`` needs the assignee and raises when there is none, so the rows
    are closed directly: the job is settling a queue it raised, not reversing one
    person's assignment.
    """
    todos = frappe.get_all(
        "ToDo",
        filters={
            "reference_type": doctype,
            "reference_name": name,
            "status": ["in", ASSIGNMENT_STATUSES],
        },
        pluck="name",
    )
    for todo in todos:
        frappe.db.set_value("ToDo", todo, "status", "Closed")
    return len(todos)


def reconcile_role_queue(doctype: str, still_needing_attention) -> int:
    """Close the queue for every document that no longer needs attention AT ALL.

    ``still_needing_attention`` must be the UNION across every job that queues this
    DocType — passing only one job's findings would close the others' work, because the
    framework gives the document one assignment and not one per reason.
    """
    keep = set(still_needing_attention)
    cleared = 0
    for name in open_assignments(doctype):
        if name not in keep:
            cleared += clear_assignment(doctype, name)
    return cleared
