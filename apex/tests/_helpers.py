# Copyright (c) 2026, AFMCO and contributors
"""Shared test helpers: session switching, workflow-safe submit/cancel, fixtures."""

import frappe


class as_user:
    """Run a block as ``user``, restoring the previous session user on exit.

    Lower-cased on purpose — it is only ever used as ``with as_user(u):``, never
    held as a value. Restores rather than resetting to Administrator, so a nested
    block returns the caller to whatever user IT was running as.
    """

    def __init__(self, user):
        self.user = user

    def __enter__(self):
        self._prev = frappe.session.user
        frappe.set_user(self.user)
        return self

    def __exit__(self, *exc):
        frappe.set_user(self._prev)
        return False


def notification_recipients(notification_name, doc):
    """The To recipients a native Notification resolves for ``doc``.

    Renders through the Notification's own ``get_list_of_recipients``, so a
    recipient added by condition/role/field is resolved exactly as it would be on
    a real send; cc/bcc are dropped because every caller asserts on To only.
    """
    notification = frappe.get_doc("Notification", notification_name)
    context = {"doc": doc, "alert": notification, "comments": None}
    recipients, _cc, _bcc = notification.get_list_of_recipients(doc, context)
    return recipients


def set_gl_posting(enabled):
    """Flip the app-wide enable_gl_posting flag the payment router's GL gate reads."""
    apex = frappe.get_single("Apex Settings")
    apex.enable_gl_posting = 1 if enabled else 0
    apex.save(ignore_permissions=True)


def approve_rental_settlement(rs, manager):
    """Drive a Rental Settlement Draft -> Reconciled -> Approved (which submits it)
    through its native workflow as ``manager``; returns the reloaded document.

    Falls back to a direct status write + submit when the workflow is not seeded on
    this site, so the accrual assertions still run on a bench that predates it.
    """
    from frappe.model.workflow import apply_workflow, get_workflow_name

    if get_workflow_name("Rental Settlement") == "Rental Settlement Workflow":
        frappe.set_user(manager)
        apply_workflow(rs, "Reconcile")
        rs.reload()
        apply_workflow(rs, "Approve")
        frappe.set_user("Administrator")
    else:
        rs.status = "Approved"
        rs.save(ignore_permissions=True)
        rs.submit()
    rs.reload()
    return rs


def cancel_submitted_for_cleanup(doc):
    """Cancel a submitted doc during teardown so it can be deleted, respecting the
    workflow-bypass guard (``apex.apex_core.utils.workflow_guard``).

    A bare ``doc.cancel()`` on a workflow-governed doctype whose workflow has a cancel
    (docstatus-2) state is now blocked by the guard. Mirror what ``apply_workflow`` does
    — land the workflow state field on that cancel state first — so the guard sees the
    sanctioned target state and lets the cancel through. Runs as Administrator inside
    ``addCleanup`` and only needs the record gone; it is NOT a substitute for a real
    workflow transition in a test body. No-ops when the doc is not submitted, and for a
    non-workflow (or no-cancel-state) doctype falls back to a plain cancel.
    """
    from frappe.model.workflow import get_workflow, get_workflow_name
    from frappe.utils import cint

    if doc.docstatus != 1:
        return
    if get_workflow_name(doc.doctype):
        workflow = get_workflow(doc.doctype)
        cancel_state = next(
            (s.state for s in workflow.states if cint(s.doc_status) == 2), None
        )
        if cancel_state:
            doc.set(workflow.workflow_state_field, cancel_state)
    doc.cancel()


def submit_via_workflow(doc):
    """Submit a workflow-governed doc the way the workflow guard requires.

    A bare ``doc.submit()`` on a workflow-governed doctype is now refused by
    ``apex.apex_core.utils.workflow_guard`` unless the current user holds an authorized
    transition to a submit (doc_status 1) state. Tests whose subject is the controller's
    ``on_submit`` SIDE-EFFECT (not the approval gate) need a legitimate way to reach
    docstatus 1: land the PERSISTED workflow state on the first submit (doc_status 1)
    state via a raw db write —
    the same endpoint ``set_workflow_state_on_action`` force-jumped to — so both the
    guard's fast-path and Frappe's ``validate_workflow`` (which rejects a multi-hop
    in-memory state jump) see the state already at the sanctioned target, then submit.
    ``on_submit`` fires with the submit-state, exactly as a real workflow approval would.

    For a non-workflow doctype this is a plain submit. NOT a substitute for a real
    ``apply_workflow`` transition in a test that exercises the approval/self-approval gate.
    """
    from frappe.model.workflow import get_workflow, get_workflow_name
    from frappe.utils import cint

    if get_workflow_name(doc.doctype):
        workflow = get_workflow(doc.doctype)
        submit_state = next(
            (s.state for s in workflow.states if cint(s.doc_status) == 1), None
        )
        if submit_state:
            frappe.db.set_value(
                doc.doctype,
                doc.name,
                workflow.workflow_state_field,
                submit_state,
                update_modified=False,
            )
            doc.reload()
    doc.submit()


def _user(email, role):
    """Return a User with ``email``, creating it if needed, and ensure it holds
    ``role``. Idempotent: re-uses an existing user/role grant."""
    if not frappe.db.exists("User", email):
        u = frappe.get_doc({"doctype": "User", "email": email,
                            "first_name": email.split("@")[0], "send_welcome_email": 0})
        u.insert(ignore_permissions=True)
    else:
        u = frappe.get_doc("User", email)
    if role not in frappe.get_roles(email):
        u.add_roles(role)
    return email


def _project(project_name="QA Scope Project"):
    """Return a Project named ``project_name``, creating it if absent. Idempotent —
    it gives a scoped Salis user a tenant to be permitted for.

    A thin default-carrying alias over ``factories.make_project``: it was a fourth
    hand-written copy of that get-or-create, written in a shape the copy-paste
    detector could not group with the other three.
    """
    from apex.tests.factories import make_project

    return make_project(project_name)


def _grant_project(user, project):
    """Grant ``user`` a Project User Permission for ``project`` (idempotent), so the
    project-scoped Salis permission hooks admit the user's in-scope rows."""
    if not frappe.db.exists(
        "User Permission", {"user": user, "allow": "Project", "for_value": project}
    ):
        frappe.get_doc(
            {
                "doctype": "User Permission",
                "user": user,
                "allow": "Project",
                "for_value": project,
            }
        ).insert(ignore_permissions=True)
