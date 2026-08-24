# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.utils import add_to_date, get_fullname, now_datetime

from apex.apex_core.worklist.action_inbox import get_pending_actions

WORKLIST_REGISTRY: dict[str, dict] = {
    "Maintenance Request": {
        "active": ["Open", "In Progress", "Resolved"],
        "terminal": ["Closed"],
        "docstatus": 1,
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


def _mine_filters(doctype: str, states: list[str], *, recent: bool) -> dict:
    filters: dict = {"owner": frappe.session.user, "status": ["in", states]}
    if "docstatus" in WORKLIST_REGISTRY[doctype]:
        filters["docstatus"] = WORKLIST_REGISTRY[doctype]["docstatus"]
    if recent:
        filters["modified"] = [">=", add_to_date(now_datetime(), hours=-_RECENT_HOURS)]
    return filters


def _mine(doctype: str, states: list[str], *, recent: bool = False) -> list[dict]:
    if not frappe.db.exists("DocType", doctype):
        return []
    if not frappe.has_permission(doctype, "read"):
        return []
    try:
        rows = frappe.get_list(
            doctype,
            filters=_mine_filters(doctype, states, recent=recent),
            fields=["name", "status", "modified"],
            order_by="modified desc",
            limit_page_length=50,
        )
    except frappe.PermissionError:
        return []
    for r in rows:
        r["doctype"] = doctype
    return rows


def _mine_count(doctype: str, states: list[str], *, recent: bool = False) -> int:
    if not frappe.db.exists("DocType", doctype):
        return 0
    if not frappe.has_permission(doctype, "read"):
        return 0
    try:
        rows = frappe.get_list(
            doctype,
            filters=_mine_filters(doctype, states, recent=recent),
            fields=["count(name) as total"],
        )
    except frappe.PermissionError:
        return 0
    return rows[0].get("total") or 0 if rows else 0


def _collect(kind: str) -> list[dict]:
    out: list[dict] = []
    recent = kind == "terminal"
    for doctype, spec in WORKLIST_REGISTRY.items():
        out.extend(_mine(doctype, spec[kind], recent=recent))
    out.sort(key=lambda r: r.get("modified") or "", reverse=True)
    return out


def _count(kind: str) -> int:
    recent = kind == "terminal"
    return sum(
        _mine_count(doctype, spec[kind], recent=recent)
        for doctype, spec in WORKLIST_REGISTRY.items()
    )


@frappe.whitelist()
def get_my_work() -> dict:
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
    return {"value": len(get_activity_on_my_documents()["documents"])}


@frappe.whitelist()
def get_submitted_by_me_count(filters=None) -> dict:
    return {"value": _count("active")}


@frappe.whitelist()
def get_approved_last_48h_count(filters=None) -> dict:
    return {"value": _count("terminal")}
