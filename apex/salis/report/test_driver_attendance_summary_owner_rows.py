# Copyright (c) 2026, AFMCO and contributors
"""A Driver with no Project permission must still see their own attendance ( #3).

The wired list scope for Driver Attendance is project-OR-owner
(``salis.permissions.driver_attendance_query`` -> ``_driver_chain_condition(with_owner=True)``)
because the Driver role holds an ``if_owner`` read DocPerm on the DocType. The
Driver Attendance Summary report re-scoped by project ALONE, so the same Driver who
sees their rows in the list view got an empty report.

The test drives the report's ``execute`` as a Driver holding NO Project User Permission,
over one row they own and one row they do not. The two riders are the shipped fixtures;
only the attendance rows — which this class commits and therefore owns — are built.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.salis.report.driver_attendance_summary.driver_attendance_summary import execute
from apex.tests._helpers import _user

test_dependencies = ["Salis Driver"]

OWN_DRIVER_NAME = "_Test Driver"
OTHER_DRIVER_NAME = "_Test Driver Two"


class TestDriverAttendanceSummaryOwnerRows(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")

        cls.driver_user = _user("das_driver@example.com", "Driver")
        cls.other_user = _user("das_other@example.com", "Driver")

        cls.own_driver = frappe.db.get_value(
            "Salis Driver", {"full_name": OWN_DRIVER_NAME}, "name"
        )
        cls.other_driver = frappe.db.get_value(
            "Salis Driver", {"full_name": OTHER_DRIVER_NAME}, "name"
        )

        # One attendance owned by the driver under test, one owned by somebody else.
        cls.own_row = cls._attendance(cls.own_driver, cls.driver_user)
        cls.other_row = cls._attendance(cls.other_driver, cls.other_user)
        frappe.db.commit()

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        for name in (cls.own_row, cls.other_row):
            if frappe.db.exists("Driver Attendance", name):
                frappe.delete_doc("Driver Attendance", name, ignore_permissions=True, force=True)
        frappe.db.commit()
        super().tearDownClass()

    @classmethod
    def _attendance(cls, driver, owner):
        doc = frappe.get_doc(
            {
                "doctype": "Driver Attendance",
                "driver": driver,
                "attendance_date": frappe.utils.today(),
                "status": "Present",
                "worked_hours": 8,
            }
        )
        doc.insert(ignore_permissions=True)
        frappe.db.set_value("Driver Attendance", doc.name, "owner", owner, update_modified=False)
        return doc.name

    def tearDown(self):
        frappe.set_user("Administrator")
        frappe.local.cache = {}

    def _rows_as(self, user):
        frappe.set_user(user)
        frappe.local.cache = {}
        _columns, data, *_rest = execute({})
        return {row["driver"] for row in data}

    def test_driver_without_project_sees_own_rows(self):
        """The report must not be empty for a Driver whose only basis is ownership."""
        drivers = self._rows_as(self.driver_user)
        self.assertIn(self.own_driver, drivers)

    def test_driver_does_not_see_another_drivers_rows(self):
        """Ownership widens the scope to the user's OWN rows and no further."""
        drivers = self._rows_as(self.driver_user)
        self.assertNotIn(self.other_driver, drivers)

    def test_oversight_role_still_sees_everything(self):
        """The unscoped path is untouched: a Fleet Manager sees both rows."""
        manager = _user("das_fleet_mgr@example.com", "Fleet Manager")
        drivers = self._rows_as(manager)
        self.assertIn(self.own_driver, drivers)
        self.assertIn(self.other_driver, drivers)
