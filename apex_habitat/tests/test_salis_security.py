"""Security regression tests for the Salis permission layer.

These lock in the audit hardening so it cannot silently regress:

  * Fuel Approval Console (``salis.api.fuel_console``) is project-scoped
    server-side and never widens scope from a client ``project`` argument; a
    scoped supervisor cannot approve/reject a Fuel Request outside their
    permitted projects even with a blanket write grant.
  * Support Ticket is row-scoped by project for supervisors, while a Driver only
    sees the tickets they raised (if_owner).
  * An Approval Request requester cannot self-authorize at the permission layer
    (maker != checker), independent of the controller-level check.

The tests drive the permission layer directly (``frappe.set_user`` + the real
endpoints / ``frappe.has_permission``) so they exercise the same code path a
real HTTP caller hits — adversarial, cross-role coverage rather than only the
happy path.
"""

import unittest

import frappe

from apex_habitat.salis.api import fuel_console
from apex_habitat.salis.permissions import (
    approval_sod_has_permission,
    scoped_has_permission,
)
from apex_habitat.tests.test_salis_doa import _user


def _project(name):
    p = frappe.db.get_value("Project", {"project_name": name}, "name")
    if not p:
        p = frappe.get_doc({"doctype": "Project", "project_name": name}).insert(
            ignore_permissions=True
        ).name
    return p


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
    frappe.db.commit()
    return doc


class TestFuelConsoleScoping(unittest.TestCase):
    """The fuel console queue and approve/reject are project-scoped server-side."""

    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        cls.pa = _project("FuelConsole A")
        cls.pb = _project("FuelConsole B")
        # A scoped supervisor granted ONLY project A (read scope; no submit, so
        # cannot mutate a submitted Fuel Request — used for the scoping/denial
        # assertions which fire at the per-doc write check before save).
        cls.sup = _user("fc_sup@example.com", "Fleet Supervisor")
        _grant_project(cls.sup, cls.pa)
        # A scoped project manager granted ONLY project A — holds submit on Fuel
        # Request, so used for the positive in-scope approval path.
        cls.pm = _user("fc_pm@example.com", "Fleet Project Manager")
        _grant_project(cls.pm, cls.pa)
        # An unscoped oversight role (sees all projects).
        cls.mgr = _user("fc_mgr@example.com", "Fleet Manager")
        cls.veh_a = _vehicle("FC AAA 1", cls.pa)
        cls.veh_b = _vehicle("FC BBB 1", cls.pb)
        cls.fr_a = _pending_fuel_request(cls.pa, cls.veh_a)
        cls.fr_b = _pending_fuel_request(cls.pb, cls.veh_b)
        frappe.db.commit()

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        for fr in (cls.fr_a, cls.fr_b):
            doc = frappe.get_doc("Fuel Request", fr.name)
            if doc.docstatus == 1:
                doc.cancel()
            frappe.delete_doc("Fuel Request", fr.name, ignore_permissions=True, force=True)
        frappe.db.commit()

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
        # The document must remain Pending — the write was blocked.
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
        # Dedicated in-scope request so this mutation does not disturb the shared
        # fixtures relied on by the read-only queue tests.
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
        frappe.db.commit()


class TestSupportTicketScoping(unittest.TestCase):
    """Support Ticket: project row-scope for supervisors, if_owner for drivers."""

    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        cls.pa = _project("Ticket A")
        cls.pb = _project("Ticket B")
        cls.sup = _user("tk_sup@example.com", "Fleet Supervisor")
        _grant_project(cls.sup, cls.pa)
        cls.mgr = _user("tk_mgr@example.com", "Fleet Manager")
        frappe.db.commit()

    def _ticket(self, project=None, owner=None):
        return frappe._dict(
            {"doctype": "Support Ticket", "project": project, "owner": owner}
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
        # The Driver owns this project-less ticket -> scoping defers to default.
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


class TestApprovalRequestPermissionSoD(unittest.TestCase):
    """maker != checker enforced at the permission layer (not just the controller)."""

    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        cls.requester = _user("ar_req@example.com", "Fleet Manager")
        cls.other = _user("ar_other@example.com", "Fleet Manager")
        frappe.db.commit()

    def _req_doc(self, decision, requested_by=None, owner=None):
        return frappe._dict(
            {
                "doctype": "Approval Request",
                "decision": decision,
                "requested_by": requested_by,
                "owner": owner,
            }
        )

    def test_requester_cannot_authorize_own_request(self):
        doc = self._req_doc("Approved", requested_by=self.requester)
        self.assertFalse(
            approval_sod_has_permission(doc, "submit", user=self.requester)
        )
        self.assertFalse(
            approval_sod_has_permission(doc, "write", user=self.requester)
        )

    def test_creator_cannot_authorize_own_request(self):
        doc = self._req_doc("Rejected", owner=self.requester)
        self.assertFalse(
            approval_sod_has_permission(doc, "submit", user=self.requester)
        )

    def test_other_user_may_authorize(self):
        doc = self._req_doc("Approved", requested_by=self.requester)
        self.assertIsNone(
            approval_sod_has_permission(doc, "submit", user=self.other)
        )

    def test_pending_decision_is_not_an_authorization(self):
        # Saving a still-Pending request (no decision yet) is not self-approval.
        doc = self._req_doc("Pending", requested_by=self.requester)
        self.assertIsNone(
            approval_sod_has_permission(doc, "write", user=self.requester)
        )

    def test_non_authorization_ptype_defers(self):
        doc = self._req_doc("Approved", requested_by=self.requester)
        self.assertIsNone(
            approval_sod_has_permission(doc, "read", user=self.requester)
        )


if __name__ == "__main__":
    unittest.main()
