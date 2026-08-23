# Copyright (c) 2026, afmcoltd
"""Put a document in a role's desk queue, and take it back out when it is settled.

Frappe already owns this: an assignment IS a ToDo, ``_assign`` on the document is
maintained by ToDo's own handlers, and the desk renders the queue, the sidebar count and
the notification without anything written here. A scheduled job that inserts its own
alert row instead builds a second inbox the user has to learn — and, the part that
actually hurt, one that nothing ever empties.

``close_all_assignments`` is called with ``ignore_permissions`` because the queue is cleared when
the DOCUMENT settles, not when the assignee decides to close it: the person who resolves a request
is rarely the person it was assigned to, and neither should need permission over the other's ToDo.
Granting a role write on ToDo to satisfy this would let it close anyone's assignment on the site.

What follows from that is :func:`reconcile_role_queue`'s contract: the caller passes the
documents that still need attention FOR ANY REASON, not the ones its own pass flagged.
A document is queued while any condition holds and settled only when none does.
"""

from __future__ import annotations

import frappe
from frappe.desk.form import assign_to as _assign_to
from frappe.desk.form.assign_to import close_all_assignments
from frappe.utils.user import get_users_with_role

ASSIGNMENT_STATUSES = ("Open", "Overdue")


def role_holders(role: str) -> list[str]:
    """Enabled holders of ``role``, without Administrator or Guest.

    ``get_users_with_role`` resolves this in one join and already drops disabled users
    and the Administrator; Guest is dropped here because a role granted to Guest would
    otherwise queue work for nobody.
    """
    return [user for user in get_users_with_role(role) if user != "Guest"]


def role_holders_escalating(*roles: str) -> list[str]:
    """Holders of the FIRST role in ``roles`` that anyone holds, else an empty list.

    An escalation ladder, not a union: a notification meant for HR reaches System
    Manager only on a site where nobody holds HR Manager, so a configured site never
    copies the site administrator on routine HR traffic. Returning the union instead
    would make every escalation permanent once it fired one time.

    Guest is dropped by :func:`role_holders`, so a role granted to Guest cannot make a
    rung look occupied when nobody is on it.
    """
    for role in roles:
        holders = role_holders(role)
        if holders:
            return holders
    return []


def assign_role(doctype: str, name: str, role: str, description: str, priority: str = "Medium") -> int:
    """Assign one document to every holder of ``role`` WHO MAY ALREADY READ IT.

    Returns how many were assigned.

    Row scope is not advisory on this path. ``assign_to.add`` reacts to an assignee who
    cannot read the document by SHARING it with them — a DocShare, or a hard throw when
    document sharing is switched off (frappe/desk/form/assign_to.py:98-110). So fanning a
    building- or project-scoped document out to every site-wide holder of a role does not
    merely queue a ToDo naming a record they cannot open: it grants the read their row
    scope had denied. Making the framework's own ``has_permission`` call first — same
    check, same default ptype — leaves the assignment to the holders already entitled to
    the document and takes the share away as a side effect.

    Idempotent by the framework's own rule: a holder who already has an open ToDo for
    this document is skipped, so a daily job never stacks a second copy.
    """
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
    """Close every open ToDo on one document. Returns how many were closed.

    ``assign_to.remove`` needs the assignee and raises when there is none, so the whole
    queue is settled at once: the job is closing a queue it raised, not reversing one
    person's assignment. That is exactly what ``close_all_assignments`` does, and it
    routes through ``ToDo.save()``, so ``on_update`` fires and rewrites the parent's
    ``_assign``. Writing the status column directly left the assignee on the document's
    desk sidebar after the queue was settled, with nothing to show it was stale.

    ``ignore_permissions`` is left at its default (False): ``close_all_assignments``
    (frappe/desk/form/assign_to.py:154-171) already calls
    ``frappe.get_doc(doctype, name).check_permission()`` — a ``read`` check on the
    REFERENCED document, never on the ToDo — so the assignee's own permission was
    never the gate this needed to clear. Every caller already holds it: the Habitat
    and Salis scheduler jobs that reconcile the queue run as the scheduler's system
    user (Administrator), for whom every check passes, and
    ``apex.salis.api.operations_alerts.resolve_alert`` re-checks ``write`` on the
    same referenced document before calling in.
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
    if todos:
        close_all_assignments(doctype, name)
    return len(todos)


def reconcile_role_queue(doctype: str, still_needing_attention) -> int:
    """Close the queue for every document that no longer needs attention AT ALL.

    ``still_needing_attention`` must be the UNION across every job that queues this
    DocType — passing only one job's findings would close the others' work, because the
    framework gives the document one assignment and not one per reason.
    """
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
