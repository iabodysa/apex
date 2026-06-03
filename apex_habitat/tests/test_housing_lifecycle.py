# Copyright (c) 2026, AFMCO and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import getdate
from apex_habitat.tests.test_utils import ApexHabitatTestCase


class TestHousingLifecycle(ApexHabitatTestCase):
    def setUp(self):
        # Create dependencies for tests
        self.company = frappe.db.get_value("Company", {})
        if not self.company:
            comp = frappe.get_doc({
                "doctype": "Company",
                "company_name": "Test Company",
                "default_currency": "SAR",
                "country": "Saudi Arabia"
            })
            comp.insert(ignore_permissions=True)
            self.company = comp.name

        self.project = frappe.db.get_value("Project", {"company": self.company})
        if not self.project:
            self.project = frappe.db.get_value("Project", {})
        if not self.project:
            proj = frappe.get_doc({
                "doctype": "Project",
                "project_name": "Test Project",
                "company": self.company
            })
            proj.insert(ignore_permissions=True)
            self.project = proj.name

        self.employee = frappe.db.get_value("Employee", {"company": self.company})
        if not self.employee:
            self.employee = frappe.db.get_value("Employee", {})
        if not self.employee:
            emp = frappe.get_doc({
                "doctype": "Employee",
                "first_name": "Test Employee",
                "company": self.company,
                "gender": "Male",
                "date_of_birth": "1990-01-01",
                "date_of_joining": "2020-01-01",
            })
            emp.insert(ignore_permissions=True)
            self.employee = emp.name

        # Get any Cost Center
        self.cost_center = frappe.db.get_value("Cost Center", {"is_group": 0, "company": self.company}) or frappe.db.get_value("Cost Center", {"is_group": 0}) or frappe.db.get_value("Cost Center", {})

        # Create Site, Building, Room, Bed with unique names so setUp is
        # re-runnable across the class's tests: Accommodation Site/Building are
        # named by field (site_name / building_name = primary key), so a fixed
        # name collides on the second test's setUp once a submit commits the row.
        suffix = frappe.generate_hash(length=6)
        self.site = frappe.get_doc({
            "doctype": "Accommodation Site",
            "site_name": "Test Site " + suffix
        })
        self.site.insert(ignore_permissions=True)

        self.building = frappe.get_doc({
            "doctype": "Accommodation Building",
            "building_name": "Test Building " + suffix,
            "site": self.site.name,
            "total_capacity": 10,
            "default_cost_center": self.cost_center
        })
        self.building.insert(ignore_permissions=True)

        self.room = frappe.get_doc({
            "doctype": "Accommodation Room",
            "naming_series": "ROOM-.####",
            "building": self.building.name,
            "room_number": "101-" + suffix,
            "bed_capacity": 2
        })
        self.room.insert(ignore_permissions=True)

        self.bed = frappe.get_doc({
            "doctype": "Accommodation Bed",
            "naming_series": "BED-.####",
            "room": self.room.name,
            "bed_code": "B1-" + suffix
        })
        self.bed.insert(ignore_permissions=True)

    def test_checkout_preserves_assignment_history(self):
        # Create and submit assignment
        assignment = frappe.get_doc({
            "doctype": "Accommodation Assignment",
            "employee": self.employee,
            "project": self.project,
            "cost_center": self.cost_center,
            "building": self.building.name,
            "room": self.room.name,
            "bed": self.bed.name,
            "check_in_date": "2026-05-01",
            "assignment_type": "New Assignment"
        })
        assignment.insert(ignore_permissions=True)
        assignment.submit()

        self.assertEqual(assignment.docstatus, 1)
        self.assertIsNone(assignment.check_out_date)

        # Create and submit checkout
        checkout = frappe.get_doc({
            "doctype": "Accommodation Checkout",
            "assignment": assignment.name,
            "checkout_date": "2026-05-21",
            "checkout_reason": "Internal Transfer"
        })
        checkout.insert(ignore_permissions=True)
        checkout.submit()

        # Reload assignment and assert docstatus is 1 (Submitted) and check_out_date is set
        assignment.reload()
        self.assertEqual(getdate(assignment.check_out_date), getdate("2026-05-21"))
        self.assertEqual(assignment.docstatus, 1, "Assignment should not be cancelled (docstatus 2) on checkout; history should be preserved.")
        
        # Verify bed is set back to available
        self.assertEqual(frappe.db.get_value("Accommodation Bed", self.bed.name, "status"), "Available")

    def test_checkout_pending_clearance_resolves_employee_name(self):
        """Checkout Pending Clearance shows the employee's display name, not just
        the raw Employee ID (Arrivals Batch 7). Reuses the setUp housing graph."""
        from apex_habitat.habitat.report.checkout_pending_clearance.checkout_pending_clearance import (
            execute as execute_checkout_clearance,
        )

        assignment = frappe.get_doc({
            "doctype": "Accommodation Assignment",
            "employee": self.employee,
            "project": self.project,
            "cost_center": self.cost_center,
            "building": self.building.name,
            "room": self.room.name,
            "bed": self.bed.name,
            "check_in_date": "2026-05-01",
            "assignment_type": "New Assignment",
        })
        assignment.insert(ignore_permissions=True)
        assignment.submit()

        # custody_cleared defaults to 0, so this checkout is "pending clearance".
        checkout = frappe.get_doc({
            "doctype": "Accommodation Checkout",
            "assignment": assignment.name,
            "checkout_date": "2026-05-21",
            "checkout_reason": "Internal Transfer",
        })
        checkout.insert(ignore_permissions=True)
        checkout.submit()

        emp_name = frappe.db.get_value("Employee", self.employee, "employee_name")
        self.assertTrue(emp_name, "seeded employee must carry a display name for this test to be meaningful")

        columns, rows = execute_checkout_clearance({})[:2]
        self.assertIn(
            "employee_name",
            [c.get("fieldname") for c in columns],
            "report must declare an Employee Name column",
        )
        mine = [r for r in rows if r.get("name") == checkout.name]
        self.assertEqual(len(mine), 1, "the pending checkout should appear in the report exactly once")
        self.assertEqual(mine[0].get("employee"), self.employee, "row must carry the fetched Employee ID")
        self.assertEqual(
            mine[0].get("employee_name"),
            emp_name,
            "report must resolve the employee's display name, not leave it blank",
        )
