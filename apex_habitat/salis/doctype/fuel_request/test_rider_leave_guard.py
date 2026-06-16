"""T-119 — rider leave / inactive guard.

A vehicle delivery (Vehicle Handover / Vehicle Assignment) and a Fuel Request
must be REJECTED when the rider (mandub) who would receive the company vehicle or
fuel is on leave or inactive, and a clearance/settlement task must be opened for
the Movement Supervisor to recover the vehicle + custody.

Source of truth (native-first):
  * HRMS Employee.status (Inactive / Left / Suspended) — covered when HRMS is
    installed on the bench;
  * an approved HRMS Leave Application covering today — likewise;
  * the local Salis Driver.status (Stopped / On Leave / Released) — always
    available, so it carries the controller-rejection assertions here.

The clearance task is a native ToDo assigned to the supervisor, deduped on an
open ToDo for the rider so re-runs never spam duplicates.

``test_ignore`` prunes the auto-dependency walk: Salis Driver links to Employee
(which pulls the ERPNext HR masters) and the Movement docs link to Salis Vehicle;
these tests build exactly the records they need with ``ignore_permissions``.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today

from apex_habitat.salis.utils import (
    raise_rider_clearance_task,
    rider_block_reason,
)

test_ignore = [
    "Employee",
    "Company",
    "Project",
    "Salis Vehicle",
    "Salis Driver",
    "User",
    "Role",
    "Leave Application",
    "Leave Type",
]


def _vehicle(plate):
    name = frappe.db.get_value("Salis Vehicle", {"plate_number": plate}, "name")
    if not name:
        name = frappe.get_doc(
            {"doctype": "Salis Vehicle", "plate_number": plate, "status": "Active"}
        ).insert(ignore_permissions=True).name
    return name


def _driver(full_name, status="Active", employee=None, supervisor=None):
    name = frappe.db.get_value("Salis Driver", {"full_name": full_name}, "name")
    if not name:
        name = frappe.get_doc(
            {
                "doctype": "Salis Driver",
                "full_name": full_name,
                "status": status,
                "employee": employee,
                "supervisor": supervisor,
            }
        ).insert(ignore_permissions=True).name
    else:
        frappe.db.set_value(
            "Salis Driver",
            name,
            {"status": status, "employee": employee, "supervisor": supervisor},
        )
    return name


def _supervisor_user():
    """An enabled user holding Fleet Supervisor, to receive the clearance task."""
    email = "t119_sup@example.com"
    if not frappe.db.exists("User", email):
        u = frappe.get_doc(
            {
                "doctype": "User",
                "email": email,
                "first_name": "T119 Sup",
                "send_welcome_email": 0,
            }
        ).insert(ignore_permissions=True)
    else:
        u = frappe.get_doc("User", email)
    if "Fleet Supervisor" not in frappe.get_roles(email):
        u.add_roles("Fleet Supervisor")
    return email


def _open_clearance_todos(driver):
    return frappe.get_all(
        "ToDo",
        filters={
            "reference_type": "Salis Driver",
            "reference_name": driver,
            "status": "Open",
        },
        pluck="name",
    )


class TestRiderLeaveGuard(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self.supervisor = _supervisor_user()

    def tearDown(self):
        frappe.set_user("Administrator")

    # [#gupim5]

    def test_active_rider_is_not_blocked(self):
        driver = _driver("T119 Active Rider", status="Active")
        self.assertIsNone(
            rider_block_reason(driver),
            "An Active rider with no leave must not be blocked.",
        )

    def test_local_driver_status_blocks(self):
        for status in ("On Leave", "Stopped", "Released"):
            driver = _driver(f"T119 {status} Rider", status=status)
            reason = rider_block_reason(driver)
            self.assertTrue(
                reason,
                f"A rider whose Salis Driver status is {status} must be blocked.",
            )

    def test_inactive_employee_blocks_when_hrms_present(self):
        """Employee Inactive/Left must block — only meaningful where HRMS/ERPNext
        Employee exists; skipped otherwise so the suite stays bench-portable."""
        if not frappe.db.exists("DocType", "Employee"):
            self.skipTest("Employee DocType not installed on this bench.")
        emp = self._left_employee("T119 Left Emp")
        # [#5oqmo6]
        driver = _driver("T119 EmpLeft Rider", status="Active", employee=emp)
        reason = rider_block_reason(driver)
        self.assertTrue(
            reason, "A rider linked to a Left Employee must be blocked."
        )

    # [#kvoqh4]

    def test_fuel_request_rejected_for_onleave_rider(self):
        driver = _driver("T119 Fuel OnLeave", status="On Leave", supervisor=self.supervisor)
        vehicle = _vehicle("T119-FUEL-1")
        fr = frappe.get_doc(
            {
                "doctype": "Fuel Request",
                "request_type": "Standard",
                "vehicle": vehicle,
                "driver": driver,
                "request_date": today(),
                "requested_litres": 40,
                "status": "Pending",
            }
        )
        with self.assertRaises(frappe.ValidationError):
            fr.insert(ignore_permissions=True)

        # [#fg9kbo]
        todos = _open_clearance_todos(driver)
        self.assertTrue(
            todos, "An on-leave rider's fuel request must open a clearance ToDo."
        )
        allocated = frappe.get_all(
            "ToDo",
            filters={"reference_type": "Salis Driver", "reference_name": driver, "status": "Open"},
            pluck="allocated_to",
        )
        self.assertIn(
            self.supervisor, allocated, "Clearance task must go to the supervisor."
        )
        self.addCleanup(lambda: self._purge_todos(driver))

    def test_vehicle_assignment_rejected_for_inactive_rider(self):
        driver = _driver("T119 VA Stopped", status="Stopped")
        vehicle = _vehicle("T119-VA-1")
        va = frappe.get_doc(
            {
                "doctype": "Vehicle Assignment",
                "vehicle": vehicle,
                "driver": driver,
                "start_date": today(),
                "status": "Active",
            }
        )
        with self.assertRaises(frappe.ValidationError):
            va.insert(ignore_permissions=True)

    def test_vehicle_handover_rejected_when_to_driver_onleave(self):
        good = _driver("T119 HO From", status="Active")
        on_leave = _driver("T119 HO To OnLeave", status="On Leave")
        vehicle = _vehicle("T119-HO-1")
        ho = frappe.get_doc(
            {
                "doctype": "Vehicle Handover",
                "vehicle": vehicle,
                "from_driver": good,
                "to_driver": on_leave,
                "handover_date": today(),
                "odometer_reading": 0,
            }
        )
        with self.assertRaises(frappe.ValidationError):
            ho.insert(ignore_permissions=True)

    def test_active_rider_fuel_request_passes(self):
        driver = _driver("T119 Fuel Active", status="Active")
        vehicle = _vehicle("T119-FUEL-OK")
        fr = frappe.get_doc(
            {
                "doctype": "Fuel Request",
                "request_type": "Standard",
                "vehicle": vehicle,
                "driver": driver,
                "request_date": today(),
                "requested_litres": 40,
                "status": "Pending",
            }
        )
        fr.insert(ignore_permissions=True)  # [#3vfaf1]
        self.assertTrue(fr.name)
        self.assertFalse(
            _open_clearance_todos(driver),
            "An active rider must not trigger a clearance task.",
        )
        self.addCleanup(lambda: frappe.delete_doc("Fuel Request", fr.name, force=True, ignore_permissions=True))

    def test_clearance_task_is_idempotent(self):
        driver = _driver("T119 Idem Rider", status="On Leave", supervisor=self.supervisor)
        first = raise_rider_clearance_task(driver, vehicle=None)
        second = raise_rider_clearance_task(driver, vehicle=None)
        self.assertEqual(len(first), 1, "First call opens exactly one clearance task.")
        self.assertEqual(second, [], "A re-run must not open a duplicate task.")
        self.assertEqual(
            len(_open_clearance_todos(driver)), 1,
            "Only one open clearance ToDo may exist for the rider.",
        )
        self.addCleanup(lambda: self._purge_todos(driver))

    # [#4lslw6]

    @staticmethod
    def _left_employee(name):
        emp = frappe.db.get_value("Employee", {"employee_name": name}, "name")
        if emp:
            frappe.db.set_value("Employee", emp, "status", "Left")
            return emp
        company = frappe.db.get_value("Company", {}, "name")
        doc = frappe.get_doc(
            {
                "doctype": "Employee",
                "employee_name": name,
                "first_name": name,
                "status": "Left",
                "company": company,
                "gender": "Male",
                "date_of_birth": "1990-01-01",
                "date_of_joining": add_days(today(), -3650),
                # [#azgwcf]
                "relieving_date": add_days(today(), -1),
            }
        )
        doc.insert(ignore_permissions=True)
        return doc.name

    @staticmethod
    def _purge_todos(driver):
        for t in _open_clearance_todos(driver):
            frappe.delete_doc("ToDo", t, force=True, ignore_permissions=True)
