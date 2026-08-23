# Copyright (c) 2026, afmcoltd
"""Unified Action Inbox — aggregation read API (Apex Core).

A single "pending my action" feed: the documents awaiting THIS user's workflow
action (native ``Workflow Action`` — auto-scoped by the framework's own
``get_permission_query_conditions`` to the user's permitted roles AND
``status='Open'``), unioned with the open ``ToDo`` rows assigned to them that point
at a real document. NO new DocType — this only READS and unions native sources.
Inline Approve/Reject is applied by the page through the canonical native endpoints
(``frappe.model.workflow.get_transitions`` / ``apply_workflow``), never here.

Owner-confirmed scope: show ONLY what awaits the user's action; exclude anything
already approved / already moved on / done. There is NO Delegation-of-Authority and
NO time window — ``status='Open'`` is the exact native signal (a Workflow Action is
flipped to Completed the instant its document transitions), and a render-time
staleness guard drops any Open row whose document has since moved past that state.
"""

from __future__ import annotations

import frappe
from frappe.model.workflow import get_transitions, get_workflow_name, get_workflow_state_field


_PAGE_WORKFLOW_ACTIONS = 200

_PAGE_TODOS = 100


@frappe.whitelist()
def get_pending_actions() -> dict:
    """Return ``{workflow_actions, todos}`` awaiting the current user's action,
    capped at the page's render budget. Each workflow action already carries its
    resolved ``transitions``, so the page can draw its buttons straight away."""
    result = _pending(_PAGE_WORKFLOW_ACTIONS, _PAGE_TODOS)
    _attach_transitions(result["workflow_actions"])
    return result


def _attach_transitions(workflow_actions: list) -> None:
    """Resolve each row's allowed transitions in place, one ``get_doc`` per row on
    the server that already read the row — not one HTTP round trip per row from the
    page before a single Approve button could be drawn. A row whose transitions
    cannot be resolved (permission denied, document moved on since the read) gets an
    empty list rather than aborting the whole inbox."""
    for row in workflow_actions:
        try:
            doc = frappe.get_doc(row["reference_doctype"], row["reference_name"])
            row["transitions"] = get_transitions(doc, raise_exception=False)
        except Exception:
            row["transitions"] = []


def _pending(workflow_limit: int, todo_limit: int) -> dict:
    """The two queues, each read to the given cap (0 meaning no cap).

    ``frappe.get_list`` (frappe/__init__.py:2008) rather than ``get_all``, so both
    queues carry the caller's own row scope: a Workflow Action names a document, and
    ``get_all`` would list actions on documents the caller cannot open.
    """
    workflow_actions = frappe.get_list(
        "Workflow Action",
        filters={"status": "Open"},
        fields=["name", "reference_doctype", "reference_name", "workflow_state", "creation"],
        order_by="creation asc",
        limit_page_length=workflow_limit,
    )
    workflow_actions = _drop_stale(workflow_actions)
    for wa in workflow_actions:
        wa["source"] = "workflow"

    todos = frappe.get_list(
        "ToDo",
        filters={
            "status": "Open",
            "allocated_to": frappe.session.user,
            "reference_type": ["is", "set"],
        },
        fields=[
            "name",
            "reference_type as reference_doctype",
            "reference_name",
            "description",
            "priority",
            "date",
            "creation",
        ],
        order_by="date asc",
        limit_page_length=todo_limit,
    )
    for td in todos:
        td["source"] = "todo"

    return {"workflow_actions": workflow_actions, "todos": todos}


@frappe.whitelist()
def get_pending_action_count(filters=None) -> dict:
    """Number-card value: how many documents await the current user's action
    (workflow approvals + assigned ToDos). Same native scoping and staleness guard as
    the page. ``filters`` is accepted and ignored — the native Custom Number Card widget
    always passes it.

    Read WITHOUT the page's caps: those are a render budget, and counting through them
    froze the card at 300 no matter how much was actually waiting. The staleness guard
    needs the rows, so this cannot become a plain SQL count.
    """
    pending = _pending(0, 0)
    return {"value": len(pending["workflow_actions"]) + len(pending["todos"])}


def _drop_stale(rows: list) -> list:
    """Keep only Workflow Actions whose document still sits at the recorded state.

    A direct DB write / import / deactivated workflow can leave an Open Workflow
    Action pointing at a document that has already moved on. We resolve each
    doctype's live workflow state field (never hard-coding ``status``) with ONE bulk
    read per doctype (no N+1) and drop rows whose document no longer matches. On any
    resolution error we KEEP the rows — never hide a legitimately-pending action.
    """
    if not rows:
        return rows

    by_doctype: dict[str, list] = {}
    for r in rows:
        by_doctype.setdefault(r["reference_doctype"], []).append(r)

    kept: list = []
    for doctype, group in by_doctype.items():
        if not frappe.db.exists("DocType", doctype):
            frappe.logger().info(
                f"action_inbox: dropped {len(group)} Open action(s) for missing DocType {doctype!r}"
            )
            continue
        try:
            workflow = get_workflow_name(doctype)
            state_field = get_workflow_state_field(workflow) if workflow else None
            if not state_field:
                kept.extend(group)
                continue
            names = [r["reference_name"] for r in group]
            live = {
                d.name: d.get(state_field)
                for d in frappe.get_all(
                    doctype, filters={"name": ["in", names]}, fields=["name", state_field]
                )
            }
            kept.extend(r for r in group if live.get(r["reference_name"]) == r["workflow_state"])
        except Exception:
            frappe.log_error(title="action_inbox staleness check")
            kept.extend(group)
    return kept
