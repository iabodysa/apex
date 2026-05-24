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
                "gender": "Male"
            })
            emp.insert(ignore_permissions=True)
            self.employee = emp.name

        # Get any Cost Center
        self.cost_center = frappe.db.get_value("Cost Center", {"is_group": 0, "company": self.company}) or frappe.db.get_value("Cost Center", {"is_group": 0}) or frappe.db.get_value("Cost Center", {})

        # Create Site, Building, Room, Bed
        self.site = frappe.get_doc({
            "doctype": "Accommodation Site",
            "site_name": "Test Site"
        })
        self.site.insert(ignore_permissions=True)

        self.building = frappe.get_doc({
            "doctype": "Accommodation Building",
            "building_name": "Test Building",
            "site": self.site.name,
            "total_capacity": 10,
            "default_cost_center": self.cost_center
        })
        self.building.insert(ignore_permissions=True)

        self.room = frappe.get_doc({
            "doctype": "Accommodation Room",
            "naming_series": "ROOM-.####",
            "building": self.building.name,
            "room_number": "101",
            "bed_capacity": 2
        })
        self.room.insert(ignore_permissions=True)

        self.bed = frappe.get_doc({
            "doctype": "Accommodation Bed",
            "naming_series": "BED-.####",
            "room": self.room.name,
            "bed_code": "B1"
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
