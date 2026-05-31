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
users, exercising the same path a desk action takes. Driver Clearance is NOT
project-scoped, so no Project User Permission is required.
"""

import unittest

import frappe
from frappe.model.workflow import apply_workflow, get_transitions, get_workflow_name

from apex_habitat.tests._helpers import _user

WORKFLOW = "Driver Clearance Workflow"


def _actions(doc):
    """The set of workflow action names currently available to the session user."""
    return {t.action for t in get_transitions(doc)}


@unittest.skipUnless(
    get_workflow_name("Driver Clearance") == WORKFLOW,
    "Driver Clearance Workflow not seeded on this site",
)
class TestDriverClearanceWorkflow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        cls.supervisor = _user("dc_sup@example.com", "Fleet Supervisor")
        cls.manager = _user("dc_mgr@example.com", "Fleet Manager")
        frappe.db.commit()

    def setUp(self):
        frappe.set_user("Administrator")

    def tearDown(self):
        frappe.set_user("Administrator")

    # --- fixtures --------------------------------------------------------------

    def _driver(self, name, vehicle=None):
        d = frappe.db.get_value("Salis Driver", {"full_name": name}, "name")
        if not d:
            d = frappe.get_doc(
                {"doctype": "Salis Driver", "full_name": name, "status": "Active"}
            ).insert(ignore_permissions=True).name
        if vehicle:
            frappe.db.set_value("Salis Driver", d, "current_vehicle", vehicle)
        return d

    def _vehicle(self, plate):
        v = frappe.db.get_value("Salis Vehicle", {"plate_number": plate}, "name")
        if not v:
            v = frappe.get_doc(
                {"doctype": "Salis Vehicle", "plate_number": plate, "status": "Active"}
            ).insert(ignore_permissions=True).name
        return v

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

    # --- legal transition by the right role ------------------------------------

    def test_legal_start_then_clear(self):
        driver = self._driver("DC Driver Legal")
        dc = self._new_clearance(driver)

        frappe.set_user(self.supervisor)
        self.assertIn("Start Processing", _actions(dc))
        apply_workflow(dc, "Start Processing")
        dc.reload()
        self.assertEqual(dc.status, "In Progress")
        self.assertEqual(dc.docstatus, 0)

        # A Fleet Manager clears it (submitting the document).
        frappe.set_user(self.manager)
        self.assertIn("Clear", _actions(dc))
        apply_workflow(dc, "Clear")
        dc.reload()
        self.assertEqual(dc.status, "Cleared")
        self.assertEqual(dc.docstatus, 1)

    # --- wrong role is blocked -------------------------------------------------

    def test_supervisor_cannot_clear(self):
        driver = self._driver("DC Driver WrongRole")
        dc = self._new_clearance(driver)
        frappe.set_user(self.supervisor)
        apply_workflow(dc, "Start Processing")
        dc.reload()

        # The submitting "Clear" action is Fleet-Manager-only — not offered to a
        # Fleet Supervisor (who holds no submit right).
        frappe.set_user(self.supervisor)
        self.assertNotIn("Clear", _actions(dc))
        with self.assertRaises(frappe.ValidationError):
            apply_workflow(dc, "Clear")

    # --- Clear blocked while an open case exists, allowed when clear -----------

    def test_clear_blocked_while_open_case_then_allowed(self):
        # A fresh driver per run so the open-case counter is deterministic (the
        # _driver helper finds an existing driver by name; a unique name avoids
        # counting cases left by a prior run).
        driver = self._driver("DC Driver OpenCase " + frappe.generate_hash(length=6))
        fec = self._open_fuel_exception(driver)
        dc = self._new_clearance(driver)

        frappe.set_user(self.supervisor)
        apply_workflow(dc, "Start Processing")
        dc.reload()
        # The open case is counted, so the precondition condition removes Clear.
        self.assertEqual(dc.outstanding_fuel_exceptions, 1)

        frappe.set_user(self.manager)
        self.assertNotIn("Clear", _actions(dc))
        with self.assertRaises(frappe.ValidationError):
            apply_workflow(dc, "Clear")

        # Resolve the case (set the closed status directly — this test exercises
        # the Driver Clearance counter, not the Fuel Exception Case state machine)
        # and re-validate the clearance so the counter refreshes.
        frappe.set_user("Administrator")
        frappe.db.set_value("Fuel Exception Case", fec.name, "status", "Resolved")
        frappe.db.commit()
        dc.reload()
        dc.save(ignore_permissions=True)  # recompute outstanding counters
        dc.reload()
        self.assertEqual(dc.outstanding_fuel_exceptions, 0)

        # Now Clear is offered and succeeds.
        frappe.set_user(self.manager)
        self.assertIn("Clear", _actions(dc))
        apply_workflow(dc, "Clear")
        dc.reload()
        self.assertEqual(dc.status, "Cleared")
        self.assertEqual(dc.docstatus, 1)

    def test_clear_blocked_while_returns_incomplete(self):
        # The same condition gates on the three return checkboxes.
        driver = self._driver("DC Driver NoReturn")
        dc = self._new_clearance(driver, returned=False)
        frappe.set_user(self.supervisor)
        apply_workflow(dc, "Start Processing")
        dc.reload()
        frappe.set_user(self.manager)
        self.assertNotIn("Clear", _actions(dc))

    # --- on_submit release side-effect -----------------------------------------

    def test_clear_releases_driver_and_clears_vehicle(self):
        vehicle = self._vehicle("DC-REL-1")
        driver = self._driver("DC Driver Release", vehicle=vehicle)
        self.assertEqual(
            frappe.db.get_value("Salis Driver", driver, "current_vehicle"), vehicle
        )

        dc = self._new_clearance(driver)
        frappe.set_user(self.manager)
        # Clear directly from Open (a Manager path exists from Open too).
        self.assertIn("Clear", _actions(dc))
        apply_workflow(dc, "Clear")
        frappe.set_user("Administrator")
        dc.reload()
        self.assertEqual(dc.status, "Cleared")

        # Side-effect: driver -> Released and current_vehicle cleared.
        driver_row = frappe.db.get_value(
            "Salis Driver", driver, ["status", "current_vehicle"], as_dict=True
        )
        self.assertEqual(driver_row.status, "Released")
        self.assertIsNone(driver_row.current_vehicle)

    # --- post-submit transition is REACHABLE (the bug being fixed) -------------

    def test_post_submit_cancel_reachable(self):
        driver = self._driver("DC Driver PostSubmit")
        dc = self._new_clearance(driver)
        frappe.set_user(self.manager)
        apply_workflow(dc, "Clear")
        dc.reload()
        self.assertEqual(dc.status, "Cleared")
        self.assertEqual(dc.docstatus, 1)

        # The frozen-post-submit bug: a transition off a docstatus=1 document is
        # reachable (Cancel -> docstatus 2).
        self.assertIn("Cancel", _actions(dc))
        apply_workflow(dc, "Cancel")
        dc.reload()
        self.assertEqual(dc.status, "Cancelled")
        self.assertEqual(dc.docstatus, 2)
