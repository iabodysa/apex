# Copyright (c) 2026, AFMCO and contributors
"""Re-validate authorization on the native-submit / native-cancel workflow bypass.

A submittable DocType governed by an active Frappe Workflow must reach docstatus 1
(submit) or 2 (cancel) ONLY through an authorized workflow transition, i.e.
``frappe.model.workflow.apply_workflow`` — which enforces the transition's role,
condition and self-approval gates. A *bare* ``doc.submit()`` / ``frappe.client.submit``
(or ``doc.cancel()``) skips all of that:

* ``set_workflow_state_on_action`` (frappe/model/workflow.py) force-jumps the state
  field to the FIRST state matching the new docstatus with NO role / condition /
  self-approval check, and
* ``validate_workflow`` only checks a transition when the state field actually
  CHANGED — which a bare submit never does.

So any user holding the DocType's native ``submit`` DocPerm could otherwise force
"Approved" (docstatus 1) on a financial / payroll / legal record, and even the
document's own author could self-approve it.

This guard closes the hole by re-validating authorization at the bare-submit level
instead of blocking outright. It is wired app-wide via ``hooks.py`` ``doc_events``
``"*"`` on ``before_submit`` and ``before_cancel`` and relies on Frappe's own call
order: ``before_submit`` runs inside ``run_before_save_methods`` (document.py) BEFORE
``_validate`` -> ``validate_workflow`` -> ``set_workflow_state_on_action``, so at guard
time the workflow state field still holds its PRE-force value.

Two paths pass the guard:

1. Fast path — ``apply_workflow`` sets the state field to the target (docstatus-1 /
   docstatus-2) state BEFORE calling ``doc.submit()`` / ``doc.cancel()``, so the current
   state's ``doc_status`` already equals the action's target docstatus. apply_workflow
   already enforced the gates, so allow.
2. Authorized bare transition — a bare submit/cancel that would force-jump the docstatus
   is allowed ONLY if the CURRENT user holds an authorized workflow transition from the
   current state to a target-docstatus state. ``get_transitions`` filters by the user's
   roles AND the transition condition; ``has_approval_access`` then enforces the
   self-approval gate (same two-part check ``apply_workflow`` and
   ``get_common_transition_actions`` apply). NB: ``get_transitions`` does NOT itself apply
   ``has_approval_access`` — the self-approval gate must be applied here explicitly.

Net effect: Administrator and any legitimately-authorized approver pass (so the app's
pervasive convention of bare-submitting workflow docs in controller unit tests as an
authorized user keeps working); an attacker with only the native ``submit`` DocPerm but
no authorized transition, and a self-approval attempt (owner == user,
``allow_self_approval = 0``), are blocked.

``get_workflow_name`` is cached, so the check is cheap and the ``"*"`` wiring safely
no-ops for every non-workflow (and post-submit ``update_after_submit``) path.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.workflow import (
    can_cancel_document,
    get_transitions,
    get_workflow,
    get_workflow_name,
    has_approval_access,
)
from frappe.utils import cint

_MESSAGE = "Approve or cancel this document through its workflow action; a direct submit or cancel is not allowed."


def _enforce(doc, target_docstatus: int) -> None:
    """Allow only an authorized workflow transition to reach ``target_docstatus``.

    Fast-path allows the ``apply_workflow`` case (current state already carries
    ``target_docstatus``). Otherwise a bare submit/cancel force-jump is allowed only
    when the current user holds an authorized transition (role + condition via
    ``get_transitions``, self-approval via ``has_approval_access``) from the current
    state to a state whose ``doc_status`` equals ``target_docstatus`` — mirroring
    ``apply_workflow``'s gate. Otherwise raise ``frappe.PermissionError``."""
    if not get_workflow_name(doc.doctype):
        return

    workflow = get_workflow(doc.doctype)
    current_state = doc.get(workflow.workflow_state_field)
    state_row = next((s for s in workflow.states if s.state == current_state), None)

    if state_row is not None and cint(state_row.doc_status) == target_docstatus:
        return

    if current_state:
        user = frappe.session.user
        target_states = {
            s.state for s in workflow.states if cint(s.doc_status) == target_docstatus
        }
        for transition in get_transitions(doc):
            if transition.next_state in target_states and has_approval_access(
                user, doc, transition
            ):
                return

    frappe.throw(_(_MESSAGE), frappe.PermissionError)


def before_submit(doc, method=None):
    _enforce(doc, 1)


def before_cancel(doc, method=None):
    if not get_workflow_name(doc.doctype) or can_cancel_document(doc.doctype):
        return
    _enforce(doc, 2)
