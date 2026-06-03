"""My Work Center — a permission-safe, Oracle-style worklist aggregator (Path A).

ONE read API that unions the four surfaces a user cares about, each scoped to the
*current user* and to that user's *real Frappe permissions*:

  1. awaiting_action   — documents awaiting THIS user's workflow action / assignment
                         (delegated to the native Action Inbox: open Workflow Action
                         rows the framework scopes to the user + open ToDos).
  2. my_open_submitted — documents the user CREATED (``owner == session user``) that
                         are still in an active (non-terminal) state.
  3. my_recent_closed  — the user's created documents that reached a terminal state
                         within the last 48 hours.
  4. my_notifications  — the user's own ``Notification Log`` rows.

This is the live aggregator (the source of truth) — NO new DocType, NO cache. Every
row is read with ``frappe.get_list`` (NOT ``get_all``), so DocPerms +
``permission_query_conditions`` apply; ``owner == session user`` is the "mine"
filter. A document is never exposed because of a role name — only because the user
owns it, is assigned it, or holds a native open Workflow Action on it. Workflow
transitions stay with the native endpoints (handled by the Action Inbox page).
"""

from __future__ import annotations

import frappe
from frappe.utils import add_to_date, now_datetime

from apex_habitat.apex_core.action_inbox import get_pending_actions

# Per-DocType worklist registry. state_field is "status" for every participating
# DocType; "mine" is always ``owner == session user`` (the creator — universal and
# permission-safe). active = still needs something; terminal = done/closed/rejected.
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
    """Union one surface ("active" or "terminal") across the whole registry."""
    out: list[dict] = []
    recent = kind == "terminal"
    for doctype, spec in WORKLIST_REGISTRY.items():
        out.extend(_mine(doctype, spec[kind], recent=recent))
    out.sort(key=lambda r: r.get("modified") or "", reverse=True)
    return out


@frappe.whitelist()
def get_my_work() -> dict:
    """The full work center: the four user-scoped, permission-safe surfaces."""
    awaiting = get_pending_actions()  # surface 1 — native, already scoped + stale-guarded
    my_notifications = frappe.get_list(
        "Notification Log",
        filters={"for_user": frappe.session.user},
        fields=["name", "subject", "type", "document_type", "document_name", "read", "creation"],
        order_by="creation desc",
        limit_page_length=20,
    )
    return {
        "awaiting_action": awaiting,
        "my_open_submitted": _collect("active"),
        "my_recent_closed": _collect("terminal"),
        "my_notifications": my_notifications,
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
