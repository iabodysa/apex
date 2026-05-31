"""Native Workflow tests for Support Ticket (Workflow Spine).

These lock in the conversion of Support Ticket from a hand-rolled status machine
to the native **Support Ticket Workflow**, and prove the staff/driver boundary:
the desk progression (New -> In Progress -> Waiting -> Resolved -> Closed, plus
Reopen and a Cancel off Closed) is staff-only. A Driver may open a ticket and
read their own (the ``if_owner`` Driver DocPerm), but the resolve/close
transitions are not offered to a Driver.

Coverage (adversarial / cross-role, not only the happy path):
  * a legal transition by the right role passes (a Fleet Supervisor starts work,
    resolves, then closes — Close submits the document);
  * a Driver cannot resolve or close (no such transition is offered, and a
    direct apply_workflow raises);
  * a Driver sees only their own ticket (the ``if_owner`` rule defers through
    scoped_has_permission for a project-less own ticket, and a scoped staff user
    is bound to their granted project);
  * a **post-submit transition is reachable** (Closed -> Cancelled on a
    docstatus=1 document) — the frozen-post-submit bug being fixed.

The tests drive the real ``frappe.model.workflow.apply_workflow`` as concrete
users, exercising the same path a desk action takes. Support Ticket is
project-scoped, so a scoped staff user is granted a Project User Permission
(mirroring test_transport_request_workflow).
"""

import unittest

import frappe
from frappe.model.workflow import apply_workflow, get_transitions, get_workflow_name

from apex_habitat.salis.permissions import scoped_has_permission
from apex_habitat.tests._helpers import _user

WORKFLOW = "Support Ticket Workflow"


def _actions(doc):
    """The set of workflow action names currently available to the session user."""
    return {t.action for t in get_transitions(doc)}


@unittest.skipUnless(
    get_workflow_name("Support Ticket") == WORKFLOW,
    "Support Ticket Workflow not seeded on this site",
)
class TestSupportTicketWorkflow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        cls.supervisor = _user("tk_wf_sup@example.com", "Fleet Supervisor")
        cls.manager = _user("tk_wf_mgr@example.com", "Fleet Manager")
        cls.driver = _user("tk_wf_driver@example.com", "Driver")
        cls.project = cls._project("Ticket Workflow Project")
        # The scoped Fleet Supervisor needs a Project User Permission to
        # read/transition project-scoped Support Tickets.
        if not frappe.db.exists(
            "User Permission",
            {"user": cls.supervisor, "allow": "Project", "for_value": cls.project},
        ):
            frappe.get_doc({
                "doctype": "User Permission",
                "user": cls.supervisor,
                "allow": "Project",
                "for_value": cls.project,
            }).insert(ignore_permissions=True)
        frappe.db.commit()

    def setUp(self):
        frappe.set_user("Administrator")

    def tearDown(self):
        frappe.set_user("Administrator")

    @staticmethod
    def _project(name):
        p = frappe.db.get_value("Project", {"project_name": name}, "name")
        if not p:
            p = frappe.get_doc(
                {"doctype": "Project", "project_name": name}
            ).insert(ignore_permissions=True).name
        return p

    _UNSET = object()

    def _new_ticket(self, project=_UNSET, **overrides):
        """A draft (status New) Support Ticket in ``self.project`` by default; pass
        ``project=None`` for a project-less ticket."""
        data = {
            "doctype": "Support Ticket",
            "raised_by": "Administrator",
            "category": "Vehicle",
            "subject": "Workflow ticket",
            "project": self.project if project is self._UNSET else project,
            "status": "New",
        }
        data.update(overrides)
        return frappe.get_doc(data).insert(ignore_permissions=True)

    # --- legal transition by the right role ------------------------------------

    def test_legal_progression_to_closed(self):
        t = self._new_ticket()

        frappe.set_user(self.supervisor)
        self.assertIn("Start Work", _actions(t))
        apply_workflow(t, "Start Work")
        t.reload()
        self.assertEqual(t.status, "In Progress")
        self.assertEqual(t.docstatus, 0)

        self.assertIn("Resolve", _actions(t))
        apply_workflow(t, "Resolve")
        t.reload()
        self.assertEqual(t.status, "Resolved")
        self.assertEqual(t.docstatus, 0)

        # Close submits the document (docstatus 0 -> 1).
        self.assertIn("Close", _actions(t))
        apply_workflow(t, "Close")
        t.reload()
        self.assertEqual(t.status, "Closed")
        self.assertEqual(t.docstatus, 1)

    def _driver_owned_ticket(self):
        """A project-less ticket owned by the Driver (the way a driver raises one
        via the portal), so the Driver can read it via the if_owner DocPerm."""
        frappe.set_user(self.driver)
        try:
            doc = frappe.get_doc({
                "doctype": "Support Ticket",
                "raised_by": self.driver,
                "category": "Vehicle",
                "subject": "Driver workflow ticket",
                "status": "New",
            }).insert()
        finally:
            frappe.set_user("Administrator")
        return doc

    # --- a Driver cannot resolve / close ---------------------------------------

    def test_driver_cannot_start_work_or_close_own_ticket(self):
        # The Driver owns the ticket (can read it via if_owner) but holds no
        # staff role, so no staff transition is offered and a direct attempt is
        # rejected by the workflow.
        t = self._driver_owned_ticket()
        frappe.set_user(self.driver)
        offered = _actions(t)
        self.assertNotIn("Start Work", offered)
        self.assertNotIn("Resolve", offered)
        self.assertNotIn("Close", offered)
        with self.assertRaises(frappe.ValidationError):
            apply_workflow(t, "Start Work")
        with self.assertRaises(frappe.ValidationError):
            apply_workflow(t, "Close")

    def test_staff_can_resolve_driver_ticket_but_driver_cannot(self):
        # Staff progress the driver's ticket to Resolved; the Driver is still
        # offered no Close/Reopen on it.
        t = self._driver_owned_ticket()
        frappe.set_user(self.manager)  # unscoped, can act on a project-less ticket
        apply_workflow(t, "Start Work")
        t.reload()
        apply_workflow(t, "Resolve")
        t.reload()
        self.assertEqual(t.status, "Resolved")

        frappe.set_user(self.driver)
        offered = _actions(t)
        self.assertNotIn("Close", offered)
        self.assertNotIn("Reopen", offered)
        with self.assertRaises(frappe.ValidationError):
            apply_workflow(t, "Close")

    # --- a Driver sees only their own (if_owner) -------------------------------

    def test_driver_sees_only_own_ticket(self):
        # A Driver's own project-less ticket defers to if_owner (allowed)...
        own = frappe._dict(
            {"doctype": "Support Ticket", "project": None, "owner": self.driver}
        )
        self.assertIsNone(
            scoped_has_permission(own, "read", user=self.driver)
        )
        # ...but a ticket owned by someone else is blocked for the Driver.
        other = frappe._dict(
            {"doctype": "Support Ticket", "project": None, "owner": "someone_else@example.com"}
        )
        self.assertFalse(
            scoped_has_permission(other, "read", user=self.driver)
        )

    def test_scoped_supervisor_bound_to_project(self):
        # The scoped supervisor is allowed in their granted project...
        in_scope = frappe._dict(
            {"doctype": "Support Ticket", "project": self.project}
        )
        self.assertIsNone(
            scoped_has_permission(in_scope, "read", user=self.supervisor)
        )
        # ...and denied in a project they were not granted.
        other_project = self._project("Ticket Workflow Other")
        out_scope = frappe._dict(
            {"doctype": "Support Ticket", "project": other_project}
        )
        self.assertFalse(
            scoped_has_permission(out_scope, "read", user=self.supervisor)
        )

    # --- post-submit transition is REACHABLE (the bug being fixed) -------------

    def test_post_submit_cancel_reachable(self):
        t = self._new_ticket()
        frappe.set_user(self.supervisor)
        apply_workflow(t, "Start Work")
        t.reload()
        apply_workflow(t, "Resolve")
        t.reload()
        apply_workflow(t, "Close")
        t.reload()
        self.assertEqual(t.status, "Closed")
        self.assertEqual(t.docstatus, 1)

        # The frozen-post-submit bug: a transition off a docstatus=1 document is
        # reachable (Cancel -> docstatus 2).
        frappe.set_user(self.manager)
        self.assertIn("Cancel", _actions(t))
        apply_workflow(t, "Cancel")
        t.reload()
        self.assertEqual(t.status, "Cancelled")
        self.assertEqual(t.docstatus, 2)
