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
from frappe.model.workflow import get_workflow_name, get_workflow_state_field


@frappe.whitelist()
def get_pending_actions() -> dict:
    """Return ``{workflow_actions, todos}`` awaiting the current user's action."""
    # [#6j7h3j]
    workflow_actions = frappe.get_list(
        "Workflow Action",
        filters={"status": "Open"},
        fields=["name", "reference_doctype", "reference_name", "workflow_state", "creation"],
        order_by="creation asc",
        limit_page_length=200,
    )
    workflow_actions = _drop_stale(workflow_actions)
    for wa in workflow_actions:
        wa["source"] = "workflow"

    # [#nzn8cw]
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
        limit_page_length=100,
    )
    for td in todos:
        td["source"] = "todo"

    return {"workflow_actions": workflow_actions, "todos": todos}


@frappe.whitelist()
def get_pending_action_count(filters=None) -> dict:
    """Number-card value: how many documents await the current user's action
    (workflow approvals + assigned ToDos). Reuses :func:`get_pending_actions`, so
    the same native scoping and staleness guard apply. ``filters`` is accepted and
    ignored — the native Custom Number Card widget always passes it."""
    pending = get_pending_actions()
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
        # [#6vdo8h]
        if not frappe.db.exists("DocType", doctype):
            frappe.logger().info(
                f"action_inbox: dropped {len(group)} Open action(s) for missing DocType {doctype!r}"
            )
            continue
        try:
            workflow = get_workflow_name(doctype)
            state_field = get_workflow_state_field(workflow) if workflow else None
            if not state_field:
                kept.extend(group)  # [#o4elq9]
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
