from __future__ import annotations
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import call, patch

from apex.salis.doctype.driver_clearance import driver_clearance
import frappe
from frappe.email.doctype.notification.notification import get_context
from frappe.model.workflow import apply_workflow
from frappe.tests.utils import FrappeTestCase
from frappe.model.workflow import apply_workflow, get_transitions, get_workflow_name
from apex.apex_core.doctype.masar_worker_token.masar_worker_token import (
    issue_driver_link,
    resolve_driver_token,
)
from apex.tests._helpers import _user
from apex.tests.factories import make_project, purge_doc, make_vehicle


class TestDriverClearance(TestCase):
    @patch.object(driver_clearance, "add_timeline_note")
    @patch.object(driver_clearance, "set_current_driver")
    @patch.object(driver_clearance, "lock_driver")
    @patch.object(driver_clearance, "lock_vehicle", create=True)
    @patch.object(driver_clearance, "frappe")
    def test_release_clears_both_sides_of_matching_vehicle_link(
        self, frappe, lock_vehicle, _lock_driver, set_current_driver, _timeline
    ):
        """The vehicle half goes through ``salis.utils.set_current_driver``, which clears
        ``current_driver_user`` alongside ``current_driver``. Leaving the user mirror
        behind would keep mailing the cleared rider about that vehicle."""
        doc = SimpleNamespace(
            driver="DRV-1",
            name="CLR-1",
            clearance_reason="Termination",
        )
        frappe.db.exists.return_value = True
        frappe.db.get_value.side_effect = ["VEH-1", "DRV-1"]

        driver_clearance.DriverClearance._release_driver(doc)

        lock_vehicle.assert_called_once_with("VEH-1")
        set_current_driver.assert_called_once_with("VEH-1", None)
        self.assertIn(
            call(
                "Salis Driver",
                "DRV-1",
                {"status": "Released", "current_vehicle": None},
            ),
            frappe.db.set_value.call_args_list,
        )

    @patch.object(driver_clearance, "planned_trips_for_driver")
    @patch.object(driver_clearance, "frappe")
    def test_clearing_a_driver_is_blocked_while_planned_trips_still_name_him(
        self, frappe, planned
    ):
        """Releasing a driver leaves his trips pointing at a released driver, and the
        supervisor finds out on the morning each one runs. The trips join the same
        blocked list as an unreturned chip, so one message names everything at once."""
        planned.return_value = ["DT-0031", "DT-0034"]
        doc = SimpleNamespace(
            status="Cleared",
            driver="DRV-1",
            vehicle_returned=1,
            fuel_chip_returned=1,
            custody_returned=1,
            outstanding_fuel_exceptions=0,
            outstanding_recoveries=0,
        )

        driver_clearance.DriverClearance._guard_cleared_status(doc)

        frappe.throw.assert_called_once()
        blocked = frappe.throw.call_args.args[0]
        self.assertIn("DT-0031", blocked, "the refusal must name the trips to hand over")
        self.assertIn("DT-0034", blocked)

    @patch.object(driver_clearance, "planned_trips_for_driver")
    @patch.object(driver_clearance, "frappe")
    def test_a_clearance_still_being_worked_is_not_graded_on_trips(self, frappe, planned):
        """Only Cleared is graded. An Open or In Progress clearance is a checklist
        somebody is filling in, and refusing it would stop the handover being recorded."""
        doc = SimpleNamespace(status="In Progress", driver="DRV-1")

        driver_clearance.DriverClearance._guard_cleared_status(doc)

        planned.assert_not_called()
        frappe.throw.assert_not_called()

    @patch.object(driver_clearance, "add_timeline_note")
    @patch.object(driver_clearance, "lock_driver")
    @patch.object(driver_clearance, "lock_vehicle", create=True)
    @patch.object(driver_clearance, "frappe")
    def test_release_does_not_unlink_vehicle_reassigned_to_another_driver(
        self, frappe, lock_vehicle, _lock_driver, _timeline
    ):
        doc = SimpleNamespace(
            driver="DRV-1",
            name="CLR-1",
            clearance_reason="Termination",
        )
        frappe.db.exists.return_value = True
        frappe.db.get_value.side_effect = ["VEH-1", "DRV-2"]

        driver_clearance.DriverClearance._release_driver(doc)

        lock_vehicle.assert_called_once_with("VEH-1")
        self.assertNotIn(
            call("Salis Vehicle", "VEH-1", "current_driver", None),
            frappe.db.set_value.call_args_list,
        )
        self.assertIn(
            call(
                "Salis Driver",
                "DRV-1",
                {"status": "Released", "current_vehicle": None},
            ),
            frappe.db.set_value.call_args_list,
        )

test_dependencies = ['Salis Driver', 'Employee']


# --- merged from test_driver_clearance_notification.py ---
DRIVER_NAME = "_Test Driver"
WORKER = "_Test Employee"
PORTAL_USER = "test@example.com"
class TestDriverClearanceNotification(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self.user = PORTAL_USER
        self.employee = frappe.db.get_value("Employee", {"first_name": WORKER})
        self.driver = frappe.db.get_value("Salis Driver", {"full_name": DRIVER_NAME}, "name")

        self.addCleanup(self._restore)
        driver_doc = frappe.get_doc("Salis Driver", self.driver)
        driver_doc.employee = self.employee
        driver_doc.save(ignore_permissions=True)

    def _restore(self):
        frappe.db.set_value(
            "Salis Driver", self.driver, {"employee": None, "driver_user": None}
        )

    def _fire(self, notification, doc):
        frappe.get_doc("Notification", notification).create_system_notification(
            doc, get_context(doc)
        )

    def _driver_logs(self, doctype, name):
        return frappe.get_all(
            "Notification Log",
            filters={
                "for_user": self.user,
                "document_type": doctype,
                "document_name": name,
            },
        )

    def test_driver_user_is_mirrored_onto_salis_driver(self):
        self.assertEqual(
            frappe.db.get_value("Salis Driver", self.driver, "driver_user"), self.user
        )

    def test_blocked_clearance_notifies_the_driver(self):
        clearance = frappe.get_doc(
            {
                "doctype": "Driver Clearance",
                "driver": self.driver,
                "clearance_reason": "Termination",
            }
        ).insert(ignore_permissions=True)
        clearance = apply_workflow(clearance, "Block")
        self.assertEqual(clearance.status, "Blocked")

        self.assertEqual(clearance.driver_user, self.user)

        self._fire("Salis - Blocked Driver Clearance", clearance)

        self.assertTrue(
            self._driver_logs("Driver Clearance", clearance.name),
            "the blocked driver must receive a Notification Log for their clearance",
        )


# --- merged from test_driver_clearance_workflow.py ---
WORKFLOW = "Driver Clearance Workflow"
def _actions(doc):
    """The set of workflow action names currently available to the session user."""
    return {t.action for t in get_transitions(doc)}
class TestDriverClearanceWorkflow(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # mandatory Salis workflow (salis_workflow_seed, every install/migrate);
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
        """A driver of this run's own, deleted when the test that asked for it ends.

        Reusing a driver by full_name kept it alive across runs, and each run re-pointed its
        project at that run's. The row then outlived every project it had ever named and
        blocked their deletes — including the demo builder's, whose teardown reported a
        Salis Driver nothing on the site could account for.
        """
        name = f"{name} {frappe.generate_hash(length=12)}"
        d = frappe.db.get_value("Salis Driver", {"full_name": name}, "name")
        if not d:
            d = frappe.get_doc(
                {"doctype": "Salis Driver", "full_name": name, "status": "Active",
                 "project": self.project}
            ).insert(ignore_permissions=True).name
            self.addCleanup(purge_doc, "Salis Driver", d)
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
        """Insert and submit an OPEN Fuel Exception Case against the driver.

        Left behind with no cleanup, this outlived the driver it named: a later run's
        ``purge_doc`` on that same driver name found a Fuel Exception Case still pointing
        at it and could not delete it either — including the demo builder's driver, once
        the naming series handed it back a number this row had used.
        """
        fec = frappe.get_doc(
            {
                "doctype": "Fuel Exception Case",
                "driver": driver,
                "exception_type": "Over-Consumption",
                "description": "Workflow test open case.",
                "status": "Open",
            }
        ).insert(ignore_permissions=True)
        self.addCleanup(purge_doc, "Fuel Exception Case", fec.name)
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
        # The token's name is the driver's own name (one token per driver, reissued in
        # place), left behind with no cleanup: a later run's purge_doc on that same driver
        # name found the token still pointing at it and could not delete the driver either.
        self.addCleanup(purge_doc, "Masar Worker Token", driver)
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
