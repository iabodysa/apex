# Copyright (c) 2026, AFMCO and contributors
"""Security regression tests for the Salis permission layer.

These lock in the audit hardening so it cannot silently regress:

  * Fuel Approval Console (``salis.api.fuel_console``) is project-scoped
    server-side and never widens scope from a client ``project`` argument; a
    scoped supervisor cannot approve/reject a Fuel Request outside their
    permitted projects even with a blanket write grant.
  * Support Ticket is row-scoped by project for supervisors, while a Driver only
    sees the tickets they raised (if_owner).

The tests drive the permission layer directly (``frappe.set_user`` + the real
endpoints / ``frappe.has_permission``) so they exercise the same code path a
real HTTP caller hits — adversarial, cross-role coverage rather than only the
happy path.
"""

import unittest

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.salis.api import fuel_console
from apex.salis.permissions import scoped_has_permission
from apex.tests._helpers import _user
from apex.tests.factories import make_project


def _grant_project(user, project):
    if not frappe.db.exists(
        "User Permission", {"allow": "Project", "for_value": project, "user": user}
    ):
        frappe.get_doc(
            {
                "doctype": "User Permission",
                "allow": "Project",
                "for_value": project,
                "user": user,
            }
        ).insert(ignore_permissions=True)


def _vehicle(plate, project=None):
    v = frappe.db.get_value("Salis Vehicle", {"plate_number": plate}, "name")
    if not v:
        v = frappe.get_doc(
            {
                "doctype": "Salis Vehicle",
                "plate_number": plate,
                "status": "Active",
                "project": project,
            }
        ).insert(ignore_permissions=True).name
    return v


def _pending_fuel_request(project, vehicle):
    """A Pending Fuel Request (a draft) in the given project.

    Under the Fuel Request Workflow a request awaiting approval is a draft
    (Pending maps to docstatus 0); the ``Approve`` transition is what submits it.
    So the approval-queue fixture is a draft, not a submitted document."""
    doc = frappe.get_doc(
        {
            "doctype": "Fuel Request",
            "project": project,
            "vehicle": vehicle,
            "requested_litres": 30,
            "request_date": frappe.utils.today(),
            "status": "Pending",
        }
    )
    doc.insert(ignore_permissions=True)
    return doc


class TestFuelConsoleScoping(FrappeTestCase):
    """The fuel console queue and approve/reject are project-scoped server-side."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.pa = make_project("FuelConsole A")
        cls.pb = make_project("FuelConsole B")
        cls.sup = _user("fc_sup@example.com", "Fleet Supervisor")
        _grant_project(cls.sup, cls.pa)
        cls.pm = _user("fc_pm@example.com", "Fleet Project Manager")
        _grant_project(cls.pm, cls.pa)
        cls.mgr = _user("fc_mgr@example.com", "Fleet Manager")
        cls.veh_a = _vehicle("FC AAA 1", cls.pa)
        cls.veh_b = _vehicle("FC BBB 1", cls.pb)
        cls.fr_a = _pending_fuel_request(cls.pa, cls.veh_a)
        cls.fr_b = _pending_fuel_request(cls.pb, cls.veh_b)

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        for fr in (cls.fr_a, cls.fr_b):
            doc = frappe.get_doc("Fuel Request", fr.name)
            if doc.docstatus == 1:
                doc.cancel()
            frappe.delete_doc("Fuel Request", fr.name, ignore_permissions=True, force=True)
        for user in (cls.sup, cls.pm):
            frappe.db.delete("User Permission",
                             {"allow": "Project", "for_value": cls.pa, "user": user})
        for v in (cls.veh_a, cls.veh_b):
            if frappe.db.exists("Salis Vehicle", v):
                frappe.delete_doc("Salis Vehicle", v, ignore_permissions=True, force=True)
        for p in (cls.pa, cls.pb):
            if frappe.db.exists("Project", p):
                frappe.delete_doc("Project", p, ignore_permissions=True, force=True)
        frappe.db.commit()
        super().tearDownClass()

    def tearDown(self):
        frappe.set_user("Administrator")

    def test_queue_scoped_to_permitted_projects(self):
        frappe.set_user(self.sup)
        names = {r["name"] for r in fuel_console.get_pending_fuel_requests()}
        self.assertIn(self.fr_a.name, names)
        self.assertNotIn(self.fr_b.name, names, "scoped sup must not see project B")

    def test_queue_argument_cannot_widen_scope(self):
        """Passing an out-of-scope project must NOT reveal it (no widening)."""
        frappe.set_user(self.sup)
        names = {r["name"] for r in fuel_console.get_pending_fuel_requests(project=self.pb)}
        self.assertEqual(names, set(), "out-of-scope project arg must yield empty queue")

    def test_unscoped_sees_all_projects(self):
        frappe.set_user(self.mgr)
        names = {r["name"] for r in fuel_console.get_pending_fuel_requests()}
        self.assertIn(self.fr_a.name, names)
        self.assertIn(self.fr_b.name, names)

    def test_scoped_user_cannot_approve_out_of_scope(self):
        frappe.set_user(self.sup)
        with self.assertRaises(frappe.PermissionError):
            fuel_console.approve_fuel_request(self.fr_b.name)
        self.assertEqual(
            frappe.db.get_value("Fuel Request", self.fr_b.name, "status"), "Pending"
        )

    def test_scoped_user_cannot_reject_out_of_scope(self):
        frappe.set_user(self.sup)
        with self.assertRaises(frappe.PermissionError):
            fuel_console.reject_fuel_request(self.fr_b.name, reason="nope")
        self.assertEqual(
            frappe.db.get_value("Fuel Request", self.fr_b.name, "status"), "Pending"
        )

    def test_scoped_user_can_approve_in_scope(self):
        own = _pending_fuel_request(self.pa, self.veh_a)
        frappe.set_user(self.pm)
        res = fuel_console.approve_fuel_request(own.name)
        self.assertEqual(res["status"], "Approved")
        self.assertEqual(
            frappe.db.get_value("Fuel Request", own.name, "approved_by"), self.pm
        )
        frappe.set_user("Administrator")
        own.reload()
        own.cancel()
        frappe.delete_doc("Fuel Request", own.name, ignore_permissions=True, force=True)

    # test_role_gap_gives_typed_message_not_raw_workflow_error was retired on 2026-08-16: it
    # asserted a Fleet Supervisor is not an approver, and the owner ruled the opposite that
    # day. The DocPerm now grants the role submit and the workflow lists it on Approve and
    # Reject. The sibling below still proves a blocked transition degrades to a typed message.

    def test_self_approval_gives_typed_message_not_raw_workflow_error(self):
        """An approver who is the requester is blocked by the SoD condition
        (requested_by != session.user), so the Approve transition is unavailable.
        The console must surface a typed self-approval message, not the raw
        workflow error, and leave the request Pending."""
        from frappe.model.workflow import WorkflowTransitionError

        frappe.set_user(self.pm)
        own = _pending_fuel_request(self.pa, self.veh_a)
        self.assertEqual(own.requested_by, self.pm)
        with self.assertRaises(frappe.PermissionError) as ctx:
            fuel_console.approve_fuel_request(own.name)
        self.assertNotIsInstance(ctx.exception, WorkflowTransitionError)
        self.assertIn("segregation of duties", str(ctx.exception).lower())
        self.assertEqual(
            frappe.db.get_value("Fuel Request", own.name, "status"), "Pending"
        )


class TestSupportTicketScoping(FrappeTestCase):
    """Issue (support tickets): project row-scope for supervisors, if_owner for
    drivers. Support tickets are now native ERPNext Issues; the same generic
    project/owner scoping (scoped_has_permission, wired to Issue in hooks) applies."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.pa = make_project("Ticket A")
        cls.pb = make_project("Ticket B")
        cls.sup = _user("tk_sup@example.com", "Fleet Supervisor")
        _grant_project(cls.sup, cls.pa)
        cls.mgr = _user("tk_mgr@example.com", "Fleet Manager")

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        frappe.db.delete("User Permission",
                         {"allow": "Project", "for_value": cls.pa, "user": cls.sup})
        for p in (cls.pa, cls.pb):
            if frappe.db.exists("Project", p):
                frappe.delete_doc("Project", p, ignore_permissions=True, force=True)
        frappe.db.commit()
        super().tearDownClass()

    def _ticket(self, project=None, owner=None):
        return frappe._dict(
            {"doctype": "Issue", "project": project, "owner": owner}
        )

    def test_scoped_sup_allowed_in_project(self):
        self.assertIsNone(
            scoped_has_permission(self._ticket(project=self.pa), "read", user=self.sup)
        )

    def test_scoped_sup_denied_other_project(self):
        self.assertFalse(
            scoped_has_permission(self._ticket(project=self.pb), "read", user=self.sup)
        )

    def test_driver_owned_projectless_ticket_is_allowed(self):
        """A Driver's own project-less ticket must defer to if_owner, not be
        blocked by project scoping."""
        drv_user = _user("tk_driver@example.com", "Driver")
        self.assertIsNone(
            scoped_has_permission(
                self._ticket(project=None, owner=drv_user), "read", user=drv_user
            )
        )

    def test_other_users_projectless_ticket_is_blocked_for_scoped_user(self):
        """A scoped user who does NOT own a project-less ticket is still denied."""
        self.assertFalse(
            scoped_has_permission(
                self._ticket(project=None, owner="someone_else@example.com"),
                "read",
                user=self.sup,
            )
        )

    def test_unscoped_manager_sees_everything(self):
        self.assertIsNone(
            scoped_has_permission(self._ticket(project=self.pb), "read", user=self.mgr)
        )
        self.assertIsNone(
            scoped_has_permission(self._ticket(project=None), "read", user=self.mgr)
        )


if __name__ == "__main__":
    unittest.main()
