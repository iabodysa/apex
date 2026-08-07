# Copyright (c) 2026, afmcoltd
"""My Work Center — Universal My Work workspace aggregator (Phase 1).

ONE read API that unions the surfaces a user cares about, each scoped to the
*current user* and to that user's *real Frappe permissions*:

  awaiting_action — documents awaiting THIS user's workflow action or assignment.
                   Source 1: open ``Workflow Action`` rows — the framework's own
                   ``get_permission_query_conditions`` hook in workflow_action.py
                   automatically scopes these to the session user's permitted roles
                   AND enforces ``status='Open'`` at the SQL level.  No additional
                   manual role or user filter is needed here.
                   Source 2: open ``ToDo`` rows allocated to this user that reference
                   a real document (``reference_type`` set).
  my_open_submitted / my_recent_closed — my own documents, still open and recently
                   closed, unioned across WORKLIST_REGISTRY.
  acted_on_my_documents — documents I raised that somebody else moved in the last 24h.
  my_notifications — the user's own ``Notification Log`` rows (all types), scoped by
                   ``for_user = session user`` (search-indexed; ORM enforces it too),
                   unread first.
  summary        — integer counts for badge display.

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
from frappe.utils import add_to_date, get_fullname, now_datetime

from apex.apex_core.worklist.action_inbox import get_pending_actions

WORKLIST_REGISTRY: dict[str, dict] = {
    "Maintenance Request": {
        "active": ["Open", "Assigned", "In Progress", "Reopened"],
        "terminal": ["Resolved", "Closed"],
    },
    "Resident Request": {
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

_RAISED_ACTIVITY_HOURS = 24


def _mine(doctype: str, states: list[str], *, recent: bool = False) -> list[dict]:
    """Permission-safe rows of ``doctype`` owned by the current user whose status is
    in ``states``. ``get_list`` (never ``get_all``) enforces DocPerms +
    permission_query_conditions; ``owner`` is the creator. ``recent`` adds the
    48-hour terminal window. A missing/perm-blocked DocType yields no rows, never an
    error (one bad source must not break the whole worklist)."""
    if not frappe.db.exists("DocType", doctype):
        return []
    if not frappe.has_permission(doctype, "read"):
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
    """Universal My Work surface — every queue the user cares about, in ONE response.

    Response shape, which the Action Inbox page renders section for section:
      awaiting_action       dict  — {workflow_actions: [...], todos: [...]}
      my_open_submitted     list  — my still-open submitted documents
      my_recent_closed      list  — my documents closed/approved in the last 48h
      acted_on_my_documents list  — documents I raised that SOMEBODY ELSE moved in 24h
      my_notifications      list  — my Notification Log rows, unread first
      summary               dict  — integer counts for badge display
    """
    awaiting_action = get_pending_actions()

    my_notifications = frappe.get_list(
        "Notification Log",
        filters={"for_user": frappe.session.user},
        fields=["name", "subject", "type", "document_type", "document_name", "read", "creation"],
        order_by="`read` asc, creation desc",
        limit_page_length=50,
    )

    my_open_submitted = _collect("active")
    my_recent_closed = _collect("terminal")
    acted_on_my_documents = get_activity_on_my_documents()["documents"]

    workflow_actions = awaiting_action.get("workflow_actions", [])
    todos = awaiting_action.get("todos", [])
    summary = {
        "needs_action": len(workflow_actions) + len(todos),
        "assigned": len(todos),
        "acted_on_my_documents": len(acted_on_my_documents),
        "notifications": len([n for n in my_notifications if not n.get("read")]),
    }

    return {
        "awaiting_action": awaiting_action,
        "my_open_submitted": my_open_submitted,
        "my_recent_closed": my_recent_closed,
        "acted_on_my_documents": acted_on_my_documents,
        "my_notifications": my_notifications,
        "summary": summary,
    }


def _acted_on_by_others(doctype: str, since) -> list[dict]:
    """Rows of ``doctype`` this user RAISED that somebody else last touched after
    ``since``. ``owner`` is the raiser, ``modified_by`` the actor and ``modified`` the
    moment — the three audit columns the framework writes on every DocType. ``get_list``
    (never ``get_all``) keeps DocPerms and permission_query_conditions in force, and a
    missing or perm-blocked DocType yields no rows rather than breaking the whole feed."""
    if not frappe.db.exists("DocType", doctype):
        return []
    if not frappe.has_permission(doctype, "read"):
        return []
    fields = ["name", "modified", "modified_by"]
    if frappe.get_meta(doctype).has_field("status"):
        fields.append("status")
    try:
        rows = frappe.get_list(
            doctype,
            filters={
                "owner": frappe.session.user,
                "modified_by": ["!=", frappe.session.user],
                "modified": [">=", since],
            },
            fields=fields,
            order_by="modified desc",
            limit_page_length=20,
        )
    except frappe.PermissionError:
        return []
    for r in rows:
        r["doctype"] = doctype
    return rows


@frappe.whitelist()
def get_activity_on_my_documents() -> dict:
    """Second feed: documents the user RAISED that somebody ELSE moved in the last 24h.

    Sourced from the framework's own audit columns (``owner`` / ``modified_by`` /
    ``modified``), which exist on every DocType and stay readable by the raiser. The two
    obvious alternatives cannot serve this feed: ``Version`` grants read to System
    Manager and Administrator only, so a raiser cannot read the change log of their own
    document, and it is written only where ``track_changes`` is on; ``Workflow Action``
    is narrowed by its own ``get_permission_query_conditions`` to ``status='Open'`` plus
    the reader's approver roles, so a COMPLETED action on the raiser's document is
    invisible to the raiser by construction. NO new DocType — this only reads.
    """
    since = add_to_date(now_datetime(), hours=-_RAISED_ACTIVITY_HOURS)
    rows: list[dict] = []
    for doctype in WORKLIST_REGISTRY:
        rows.extend(_acted_on_by_others(doctype, since))

    rows.sort(key=lambda r: r.get("modified") or "", reverse=True)
    rows = rows[:20]

    actors: dict[str, str] = {}
    for r in rows:
        actor = r.get("modified_by")
        if actor and actor not in actors:
            actors[actor] = get_fullname(actor)
        r["actor"] = actors.get(actor) or actor

    return {"documents": rows, "hours": _RAISED_ACTIVITY_HOURS}


@frappe.whitelist()
def get_activity_on_my_documents_count(filters=None) -> dict:
    """Custom Number Card: how many documents I raised did somebody else move in the
    last 24 hours. Reuses :func:`get_activity_on_my_documents`, so the same source and
    permission scoping apply. ``filters`` is accepted and ignored — the native Custom
    Number Card widget always passes it."""
    return {"value": len(get_activity_on_my_documents()["documents"])}


@frappe.whitelist()
def get_submitted_by_me_count(filters=None) -> dict:
    """Custom Number Card: count of my still-open submitted documents. ``filters`` is
    accepted and ignored (the native Custom Number Card widget always passes it)."""
    return {"value": len(_collect("active"))}


@frappe.whitelist()
def get_approved_last_48h_count(filters=None) -> dict:
    """Custom Number Card: count of my documents closed/approved in the last 48h."""
    return {"value": len(_collect("terminal"))}
