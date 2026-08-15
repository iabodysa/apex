# Copyright (c) 2026, AFMCO and contributors
"""Native Workflow tests for Driver Clearance (Workflow Spine, second-mover).

These lock in the conversion of Driver Clearance from a status field with no
transition engine to the native **Driver Clearance Workflow**, and prove the
exit-clearance control: the "Clear" transition (which submits the document)
is only offered once the vehicle, fuel chip and custody are returned and no
open Fuel Exception Case or Movement Cost Recovery remains against the driver.

Coverage (adversarial / cross-role, not only the happy path):
  * a legal transition by the right role passes (Fleet Supervisor starts
    processing; a Fleet Manager clears);
  * a wrong role is blocked (a Fleet Supervisor is not offered the submitting
    "Clear" action);
  * "Clear" is blocked while an open Fuel Exception Case exists (the precondition
    condition removes the action), and allowed once it is resolved;
  * the on_submit release side-effect fires: the driver -> Released and its
    current_vehicle is cleared;
  * a **post-submit transition is reachable** (Cleared -> Cancelled on a
    docstatus=1 document) — the frozen-post-submit bug being fixed.

The tests drive the real ``frappe.model.workflow.apply_workflow`` as concrete
users, exercising the same path a desk action takes. Driver Clearance is
project-scoped through its driver (Salis Driver -> project), so the scoped Fleet
Supervisor is granted a Project User Permission and every test driver is anchored
to that project; the oversight Fleet Manager needs no permission.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.model.workflow import apply_workflow, get_transitions, get_workflow_name

from apex.apex_core.doctype.masar_worker_token.masar_worker_token import (
    issue_driver_link,
    resolve_driver_token,
)
from apex.tests._helpers import _user
from apex.tests.factories import make_project, make_vehicle

WORKFLOW = "Driver Clearance Workflow"


def _actions(doc):
    """The set of workflow action names currently available to the session user."""
    return {t.action for t in get_transitions(doc)}


class TestDriverClearanceWorkflow(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # A-077: mandatory Salis workflow (salis_workflow_seed, every install/migrate);
        # absence is a regression - FAIL, never skip.
        if get_workflow_name("Driver Clearance") != WORKFLOW:
            raise AssertionError(
                f"Mandatory Salis workflow {WORKFLOW!r} not active for "
                "'Driver Clearance' (salis_workflow_seed regression)"
            )
        frappe.set_user("Administrator")
        cls.supervisor = _user("dc_sup@example.com", "Fleet Supervisor")
        cls.manager = _user("dc_mgr@example.com", "Fleet Manager")
        cls.project = make_project("DC Workflow Project")
        cls._user_perm(cls.supervisor, cls.project)

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        frappe.db.delete(
            "User Permission",
            {"allow": "Project", "for_value": cls.project, "user": cls.supervisor},
        )
        if frappe.db.exists("Project", cls.project):
            frappe.delete_doc("Project", cls.project, ignore_permissions=True, force=True)
        frappe.db.commit()
        super().tearDownClass()

    def setUp(self):
        frappe.set_user("Administrator")

    def tearDown(self):
        frappe.set_user("Administrator")

    @staticmethod
    def _user_perm(user, project):
        if not frappe.db.exists(
            "User Permission",
            {"allow": "Project", "for_value": project, "user": user},
        ):
            frappe.get_doc(
                {"doctype": "User Permission", "allow": "Project",
                 "for_value": project, "user": user}
            ).insert(ignore_permissions=True)


    def _driver(self, name, vehicle=None):
        d = frappe.db.get_value("Salis Driver", {"full_name": name}, "name")
        if not d:
            d = frappe.get_doc(
                {"doctype": "Salis Driver", "full_name": name, "status": "Active",
                 "project": self.project}
            ).insert(ignore_permissions=True).name
        else:
            frappe.db.set_value("Salis Driver", d, "project", self.project)
        if vehicle:
            frappe.db.set_value("Salis Driver", d, "current_vehicle", vehicle)
        return d

    def _new_clearance(self, driver, returned=True, **overrides):
        """A draft Driver Clearance. When ``returned`` is True the three return
        checkboxes are ticked so only outstanding cases can block clearing."""
        data = {
            "doctype": "Driver Clearance",
            "driver": driver,
            "clearance_reason": "End of Assignment",
            "vehicle_returned": 1 if returned else 0,
            "fuel_chip_returned": 1 if returned else 0,
            "custody_returned": 1 if returned else 0,
            "status": "Open",
        }
        data.update(overrides)
        return frappe.get_doc(data).insert(ignore_permissions=True)

    def _open_fuel_exception(self, driver):
        """Insert and submit an OPEN Fuel Exception Case against the driver."""
        fec = frappe.get_doc(
            {
                "doctype": "Fuel Exception Case",
                "driver": driver,
                "exception_type": "Over-Consumption",
                "description": "Workflow test open case.",
                "status": "Open",
            }
        ).insert(ignore_permissions=True)
        return fec


    def test_legal_start_then_clear(self):
        driver = self._driver("DC Driver Legal")
        dc = self._new_clearance(driver)

        frappe.set_user(self.supervisor)
        self.assertIn("Start Processing", _actions(dc))
        apply_workflow(dc, "Start Processing")
        dc.reload()
        self.assertEqual(dc.status, "In Progress")
        self.assertEqual(dc.docstatus, 0)

        frappe.set_user(self.manager)
        self.assertIn("Clear", _actions(dc))
        apply_workflow(dc, "Clear")
        dc.reload()
        self.assertEqual(dc.status, "Cleared")
        self.assertEqual(dc.docstatus, 1)


    def test_supervisor_cannot_clear(self):
        driver = self._driver("DC Driver WrongRole")
        dc = self._new_clearance(driver)
        frappe.set_user(self.supervisor)
        apply_workflow(dc, "Start Processing")
        dc.reload()

        frappe.set_user(self.supervisor)
        self.assertNotIn("Clear", _actions(dc))
        with self.assertRaises(frappe.ValidationError):
            apply_workflow(dc, "Clear")


    def test_clear_blocked_while_open_case_then_allowed(self):
        driver = self._driver("DC Driver OpenCase " + frappe.generate_hash(length=12))
        fec = self._open_fuel_exception(driver)
        dc = self._new_clearance(driver)

        frappe.set_user(self.supervisor)
        apply_workflow(dc, "Start Processing")
        dc.reload()
        self.assertEqual(dc.outstanding_fuel_exceptions, 1)

        frappe.set_user(self.manager)
        self.assertNotIn("Clear", _actions(dc))
        with self.assertRaises(frappe.ValidationError):
            apply_workflow(dc, "Clear")

        frappe.set_user("Administrator")
        frappe.db.set_value("Fuel Exception Case", fec.name, "status", "Resolved")
        dc.reload()
        dc.save(ignore_permissions=True)
        dc.reload()
        self.assertEqual(dc.outstanding_fuel_exceptions, 0)

        frappe.set_user(self.manager)
        self.assertIn("Clear", _actions(dc))
        apply_workflow(dc, "Clear")
        dc.reload()
        self.assertEqual(dc.status, "Cleared")
        self.assertEqual(dc.docstatus, 1)

    def test_clear_blocked_while_returns_incomplete(self):
        driver = self._driver("DC Driver NoReturn")
        dc = self._new_clearance(driver, returned=False)
        frappe.set_user(self.supervisor)
        apply_workflow(dc, "Start Processing")
        dc.reload()
        frappe.set_user(self.manager)
        self.assertNotIn("Clear", _actions(dc))


    def test_clear_releases_driver_and_clears_vehicle(self):
        vehicle = make_vehicle("DC-REL-1")
        driver = self._driver("DC Driver Release", vehicle=vehicle)
        self.assertEqual(
            frappe.db.get_value("Salis Driver", driver, "current_vehicle"), vehicle
        )

        dc = self._new_clearance(driver)
        frappe.set_user(self.manager)
        self.assertIn("Clear", _actions(dc))
        apply_workflow(dc, "Clear")
        frappe.set_user("Administrator")
        dc.reload()
        self.assertEqual(dc.status, "Cleared")

        driver_row = frappe.db.get_value(
            "Salis Driver", driver, ["status", "current_vehicle"], as_dict=True
        )
        self.assertEqual(driver_row.status, "Released")
        self.assertIsNone(driver_row.current_vehicle)


    def test_post_submit_cancel_reachable(self):
        driver = self._driver(
            "DC Driver PostSubmit " + frappe.generate_hash(length=12)
        )
        frappe.set_user("Administrator")
        issued = issue_driver_link(driver)
        dc = self._new_clearance(driver)
        frappe.set_user(self.manager)
        apply_workflow(dc, "Clear")
        dc.reload()
        self.assertEqual(dc.status, "Cleared")
        self.assertEqual(dc.docstatus, 1)
        self.assertEqual(
            frappe.db.get_value(
                "Masar Worker Token", {"driver": driver}, "enabled"
            ),
            0,
        )

        self.assertIn("Cancel", _actions(dc))
        apply_workflow(dc, "Cancel")
        dc.reload()
        self.assertEqual(dc.status, "Cancelled")
        self.assertEqual(dc.docstatus, 2)
        self.assertEqual(
            frappe.db.get_value(
                "Masar Worker Token", {"driver": driver}, "enabled"
            ),
            0,
        )
        with self.assertRaises(frappe.PermissionError):
            resolve_driver_token(issued["token"])

        frappe.set_user("Administrator")
        frappe.get_doc("Salis Driver", driver).db_set("status", "Active")
        with self.assertRaises(frappe.PermissionError):
            resolve_driver_token(issued["token"])
        reissued = issue_driver_link(driver)
        self.assertNotEqual(reissued["token"], issued["token"])
        self.assertEqual(resolve_driver_token(reissued["token"]), driver)
