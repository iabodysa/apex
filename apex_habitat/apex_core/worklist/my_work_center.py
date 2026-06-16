"""My Work Center — Universal My Work workspace aggregator (Phase 1).

ONE read API that unions the surfaces a user cares about, each scoped to the
*current user* and to that user's *real Frappe permissions*:

  needs_action   — documents awaiting THIS user's workflow action or assignment.
                   Source 1: open ``Workflow Action`` rows — the framework's own
                   ``get_permission_query_conditions`` hook in workflow_action.py
                   automatically scopes these to the session user's permitted roles
                   AND enforces ``status='Open'`` at the SQL level.  No additional
                   manual role or user filter is needed here.
                   Source 2: open ``ToDo`` rows allocated to this user that reference
                   a real document (``reference_type`` set).
  notifications  — the user's own ``Notification Log`` rows (all types), scoped by
                   ``for_user = session user`` (search-indexed; ORM enforces it too).
  mentions       — [] in Phase 1; deferred to Phase 2 (Notification Log type='Mention').
  field_references — [] reserved; not populated in Phase 1.
  summary        — integer counts for badge display:
                     needs_action  = len(workflow_actions) + len(todos)
                     assigned      = len(todos)  (sub-count of needs_action)
                     mentions      = 0  (Phase 1 stub)
                     notifications = len(notifications)

This is the live aggregator — NO new DocType, NO cache. Every row is read with
``frappe.get_list`` (NOT ``get_all``), so DocPerms + ``permission_query_conditions``
apply. Workflow transitions are applied by the native endpoints; this module only
reads. WORKLIST_REGISTRY (legacy per-DocType registry) is kept for
``get_submitted_by_me_count`` / ``get_approved_last_48h_count`` Number Cards that
still aggregate the user's own submitted documents — it is NOT used to source
workflow actions (those come from Frappe's native Workflow Action DocType).
"""

from __future__ import annotations

import frappe
from frappe.utils import add_to_date, now_datetime

from apex_habitat.apex_core.worklist.action_inbox import get_pending_actions

# [#ttr0oz]
# [#qxpijl]
# [#12vsj4]
# [#bdx7fz]
WORKLIST_REGISTRY: dict[str, dict] = {
    "Maintenance Request": {
        "active": ["Open", "Assigned", "In Progress", "Reopened"],
        "terminal": ["Resolved", "Closed"],
    },
    "Accommodation Resident Request": {
        "active": ["New", "Triaged", "Assigned", "In Progress", "Waiting Evidence"],
        "terminal": ["Resolved", "Rejected", "Closed"],
    },
    "Fuel Request": {
        "active": ["Pending"],
        "terminal": ["Approved", "Done", "Failed", "Reverted", "Cancelled"],
    },
    "Fuel Claim": {
        "active": ["Draft", "Submitted to Movement", "Reconciled", "Disputed"],
        "terminal": ["Approved", "Closed"],
    },
    "Transport Request": {
        "active": ["New", "Validated", "Approved", "Scheduled"],
        "terminal": ["Fulfilled", "Rejected", "Cancelled"],
    },
    "Salis Payment Request": {
        "active": ["Draft", "Pending Finance"],
        "terminal": ["Approved by Finance", "Paid", "Rejected", "Cancelled"],
    },
    "Rental Settlement": {
        "active": ["Draft", "Reconciled", "Disputed"],
        "terminal": ["Approved", "Paid", "Cancelled"],
    },
    "Scheduled Task Instance": {
        "active": ["Open", "In Progress", "Overdue"],
        "terminal": ["Completed", "Cancelled"],
    },
    "Dispatch Trip": {
        "active": ["Planned", "Dispatched"],
        "terminal": ["Completed", "Cancelled"],
    },
}

_RECENT_HOURS = 48


def _mine(doctype: str, states: list[str], *, recent: bool = False) -> list[dict]:
    """Permission-safe rows of ``doctype`` owned by the current user whose status is
    in ``states``. ``get_list`` (never ``get_all``) enforces DocPerms +
    permission_query_conditions; ``owner`` is the creator. ``recent`` adds the
    48-hour terminal window. A missing/perm-blocked DocType yields no rows, never an
    error (one bad source must not break the whole worklist)."""
    if not frappe.db.exists("DocType", doctype):
        return []
    filters: dict = {"owner": frappe.session.user, "status": ["in", states]}
    if recent:
        filters["modified"] = [">=", add_to_date(now_datetime(), hours=-_RECENT_HOURS)]
    try:
        rows = frappe.get_list(
            doctype,
            filters=filters,
            fields=["name", "status", "modified"],
            order_by="modified desc",
            limit_page_length=50,
        )
    except frappe.PermissionError:
        return []
    for r in rows:
        r["doctype"] = doctype
    return rows


def _collect(kind: str) -> list[dict]:
    """Union one surface ("active" or "terminal") across the WORKLIST_REGISTRY.
    Used ONLY for the Number Card helpers — NOT for workflow action sourcing."""
    out: list[dict] = []
    recent = kind == "terminal"
    for doctype, spec in WORKLIST_REGISTRY.items():
        out.extend(_mine(doctype, spec[kind], recent=recent))
    out.sort(key=lambda r: r.get("modified") or "", reverse=True)
    return out


@frappe.whitelist()
def get_my_work() -> dict:
    """Universal My Work workspace — five surfaces, all user-scoped and permission-safe.

    Response shape (Phase 1):
      needs_action       dict  — {workflow_actions: [...], todos: [...]}
      notifications      list  — Notification Log rows for this user (all types)
      mentions           list  — [] in Phase 1 (deferred)
      field_references   list  — [] reserved
      summary            dict  — {needs_action: int, assigned: int, mentions: int,
                                   notifications: int}
    """
    # [#5wk9av]
    # [#m9muvz]
    # [#qfbfxu]
    needs_action = get_pending_actions()  # [#3xiq2n]

    # [#fglhbi]
    # [#r22i3g]
    notifications = frappe.get_list(
        "Notification Log",
        filters={"for_user": frappe.session.user},
        fields=["name", "subject", "type", "document_type", "document_name", "read", "creation"],
        order_by="creation desc",
        limit_page_length=50,
    )

    # [#rduyys]
    mentions: list = []

    # [#ov3i3r]
    field_references: list = []

    # [#nbz4tu]
    workflow_actions = needs_action.get("workflow_actions", [])
    todos = needs_action.get("todos", [])
    summary = {
        "needs_action": len(workflow_actions) + len(todos),
        "assigned": len(todos),
        "mentions": 0,
        "notifications": len(notifications),
    }

    return {
        "needs_action": needs_action,
        "notifications": notifications,
        "mentions": mentions,
        "field_references": field_references,
        "summary": summary,
    }


@frappe.whitelist()
def get_submitted_by_me_count(filters=None) -> dict:
    """Custom Number Card: count of my still-open submitted documents. ``filters`` is
    accepted and ignored (the native Custom Number Card widget always passes it)."""
    return {"value": len(_collect("active"))}


@frappe.whitelist()
def get_approved_last_48h_count(filters=None) -> dict:
    """Custom Number Card: count of my documents closed/approved in the last 48h."""
    return {"value": len(_collect("terminal"))}
