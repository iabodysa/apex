# Copyright (c) 2026, AFMCO and contributors
"""T-119 — rider leave / inactive guard.

A vehicle delivery (Vehicle Handover / Vehicle Assignment) and a Fuel Request
must be REJECTED when the rider (mandub) who would receive the company vehicle or
fuel is on leave or inactive, and a clearance/settlement task must be opened for
the Movement Supervisor to recover the vehicle + custody.

Source of truth, in the order ``rider_block_reason`` reads them:
  * HRMS Employee.status (Inactive / Left / Suspended);
  * an approved, submitted HRMS Leave Application covering the date — the only
    leave source the app carries. ``Salis Driver.status`` has no "On Leave"
    option (Active / Stopped / Released); the retired one was folded into Stopped
    by ``apex.patches.v2_6.converge_state_contracts.driver_status``, and
    ``BLOCKING_DRIVER_STATUSES`` is pinned to ("Stopped", "Released");
  * the local Salis Driver.status (Stopped / Released).

``Salis Driver.status`` is server-owned: ``SalisDriver._refuse_a_hand_written_status``
resets a new record to Active and throws ``PermissionError`` on a hand-edited
change. A fixture therefore stamps it the way the sanctioned writers (Driver
Suspension on_submit / Driver Clearance) do — ``frappe.db.set_value``, which runs
no controller method.

The clearance task is a native ToDo assigned to the supervisor, deduped on an
open ToDo for the rider so re-runs never spam duplicates.

``test_ignore`` prunes the auto-dependency walk: Salis Driver links to Employee
(which pulls the ERPNext HR masters) and the Movement docs link to Salis Vehicle;
these tests build exactly the records they need with ``ignore_permissions``.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today

from apex.salis.utils import (
    raise_rider_clearance_task,
    rider_block_reason,
)
from apex.tests import factories

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
    "Holiday List",
]


def _driver(full_name, status="Active", employee=None, supervisor=None):
    """Get-or-create a Salis Driver carrying ``status``.

    The status is written with ``frappe.db.set_value`` rather than through the
    document, because ``SalisDriver._refuse_a_hand_written_status`` forces a new
    record to Active and refuses a change on save — a value passed to ``insert``
    silently becomes Active and the guard under test is then never reached.
    """
    name = frappe.db.get_value("Salis Driver", {"full_name": full_name}, "name")
    if not name:
        name = frappe.get_doc(
            {
                "doctype": "Salis Driver",
                "full_name": full_name,
                "employee": employee,
                "supervisor": supervisor,
            }
        ).insert(ignore_permissions=True).name
    frappe.db.set_value(
        "Salis Driver",
        name,
        {"status": status, "employee": employee, "supervisor": supervisor},
    )
    return name


def _unpaid_leave_type():
    """A Leave Without Pay type: ``is_lwp`` skips the HRMS balance check, so the
    application needs no Leave Allocation standing behind it."""
    name = "T119 Unpaid Leave"
    if not frappe.db.exists("Leave Type", name):
        frappe.get_doc(
            {"doctype": "Leave Type", "leave_type_name": name, "is_lwp": 1}
        ).insert(ignore_permissions=True)
    return name


def _empty_holiday_list():
    """A Holiday List spanning the test window with no holidays in it.

    HRMS refuses an application whose every day is a holiday, and
    ``create_leave_ledger_entry`` resolves the employee's holiday list on submit
    with ``raise_exception=True``, so the employee needs one that exists.
    """
    name = "T119 No Holidays"
    if not frappe.db.exists("Holiday List", name):
        frappe.get_doc(
            {
                "doctype": "Holiday List",
                "holiday_list_name": name,
                "from_date": add_days(today(), -730),
                "to_date": add_days(today(), 730),
            }
        ).insert(ignore_permissions=True)
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


    def test_active_rider_is_not_blocked(self):
        driver = _driver("T119 Active Rider", status="Active")
        self.assertIsNone(
            rider_block_reason(driver),
            "An Active rider with no leave must not be blocked.",
        )

    def test_local_driver_status_blocks(self):
        """Stopped and Released are the whole blocking set the master can hold —
        the Select carries only Active / Stopped / Released."""
        for status in ("Stopped", "Released"):
            driver = _driver(f"T119 {status} Rider", status=status)
            reason = rider_block_reason(driver)
            self.assertTrue(
                reason,
                f"A rider whose Salis Driver status is {status} must be blocked.",
            )

    def test_approved_leave_blocks_an_active_rider(self):
        """The leave source, reached the way the app reads it: the driver stays
        Active and the block comes from the approved HRMS Leave Application."""
        emp = self._employee_on_leave("T119 Leave Emp")
        driver = _driver("T119 Leave Rider", status="Active", employee=emp)
        reason = rider_block_reason(driver)
        self.assertTrue(
            reason, "A rider on approved leave today must be blocked."
        )

    def test_inactive_employee_blocks_when_hrms_present(self):
        """A rider whose HRMS Employee has Left must be blocked.

 hrms and erpnext are both in hooks.required_apps, so Employee is
        always installed wherever apex is. The old ``skipTest`` on its absence made
        this the one rider-block source that CI never actually exercised.
        """
        self.assertTrue(
            frappe.db.exists("DocType", "Employee"),
            "Employee must be installed — hrms is a required app",
        )
        emp = self._left_employee("T119 Left Emp")
        driver = _driver("T119 EmpLeft Rider", status="Active", employee=emp)
        reason = rider_block_reason(driver)
        self.assertTrue(
            reason, "A rider linked to a Left Employee must be blocked."
        )


    def test_fuel_request_rejected_for_onleave_rider(self):
        emp = self._employee_on_leave("T119 Fuel OnLeave Emp")
        driver = _driver(
            "T119 Fuel OnLeave", status="Active", employee=emp, supervisor=self.supervisor
        )
        vehicle = factories.make_vehicle("T119-FUEL-1")
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
        vehicle = factories.make_vehicle("T119-VA-1")
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
        on_leave = _driver(
            "T119 HO To OnLeave",
            status="Active",
            employee=self._employee_on_leave("T119 HO OnLeave Emp"),
        )
        vehicle = factories.make_vehicle("T119-HO-1")
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
        vehicle = factories.make_vehicle("T119-FUEL-OK")
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
        fr.insert(ignore_permissions=True)
        self.assertTrue(fr.name)
        self.assertFalse(
            _open_clearance_todos(driver),
            "An active rider must not trigger a clearance task.",
        )
        self.addCleanup(lambda: frappe.delete_doc("Fuel Request", fr.name, force=True, ignore_permissions=True))

    def test_clearance_task_is_idempotent(self):
        driver = _driver("T119 Idem Rider", status="Stopped", supervisor=self.supervisor)
        first = raise_rider_clearance_task(driver, vehicle=None)
        second = raise_rider_clearance_task(driver, vehicle=None)
        self.assertEqual(len(first), 1, "First call opens exactly one clearance task.")
        self.assertEqual(second, [], "A re-run must not open a duplicate task.")
        self.assertEqual(
            len(_open_clearance_todos(driver)), 1,
            "Only one open clearance ToDo may exist for the rider.",
        )
        self.addCleanup(lambda: self._purge_todos(driver))


    @staticmethod
    def _left_employee(name):
        emp = frappe.db.get_value("Employee", {"employee_name": name}, "name")
        if emp:
            frappe.db.set_value("Employee", emp, "status", "Left")
            return emp
        # Built, not assumed: an Employee needs a Company, and nothing in
        # before_tests guarantees one on a site that was never wizard-bootstrapped.
        company = factories.ensure_company()
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
                "relieving_date": add_days(today(), -1),
            }
        )
        doc.insert(ignore_permissions=True)
        return doc.name

    @staticmethod
    def _employee_on_leave(name):
        """An ACTIVE Employee carrying an approved, submitted Leave Application
        that covers today.

        The employee stays Active on purpose: that is what isolates the leave
        source from the employee-status source, both of which
        ``rider_block_reason`` reads. HRMS refuses to validate a leave for an
        inactive employee anyway.
        """
        company = factories.ensure_company()
        holiday_list = _empty_holiday_list()
        emp = frappe.db.get_value("Employee", {"employee_name": name}, "name")
        if not emp:
            emp = frappe.get_doc(
                {
                    "doctype": "Employee",
                    "employee_name": name,
                    "first_name": name,
                    "status": "Active",
                    "company": company,
                    "gender": "Male",
                    "date_of_birth": "1990-01-01",
                    "date_of_joining": add_days(today(), -3650),
                    "holiday_list": holiday_list,
                }
            ).insert(ignore_permissions=True).name

        covering = frappe.db.exists(
            "Leave Application",
            {
                "employee": emp,
                "status": "Approved",
                "docstatus": 1,
                "from_date": ["<=", today()],
                "to_date": [">=", today()],
            },
        )
        if not covering:
            leave = frappe.get_doc(
                {
                    "doctype": "Leave Application",
                    "employee": emp,
                    "company": company,
                    "leave_type": _unpaid_leave_type(),
                    "from_date": add_days(today(), -1),
                    "to_date": add_days(today(), 1),
                    "status": "Approved",
                }
            )
            leave.insert(ignore_permissions=True)
            leave.submit()
        return emp

    @staticmethod
    def _purge_todos(driver):
        for t in _open_clearance_todos(driver):
            frappe.delete_doc("ToDo", t, force=True, ignore_permissions=True)
