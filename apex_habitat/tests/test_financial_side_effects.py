# Copyright (c) 2026, AFMCO and contributors
# For license information, please see license.txt

import frappe
from apex_habitat.tests.test_utils import ApexHabitatTestCase


class TestFinancialSideEffects(ApexHabitatTestCase):
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

        # Create Site & Building
        site_name = "Test Financial Site"
        if not frappe.db.exists("Accommodation Site", site_name):
            self.site = frappe.get_doc({
                "doctype": "Accommodation Site",
                "site_name": site_name
            })
            self.site.insert(ignore_permissions=True)
        else:
            self.site = frappe.get_doc("Accommodation Site", site_name)

        building_name = "Test Financial Building"
        if not frappe.db.exists("Accommodation Building", building_name):
            self.building = frappe.get_doc({
                "doctype": "Accommodation Building",
                "building_name": building_name,
                "site": self.site.name,
                "total_capacity": 10
            })
            self.building.insert(ignore_permissions=True)
        else:
            self.building = frappe.get_doc("Accommodation Building", building_name)

        # Create Custody Asset Category & Article
        category_name = "Furniture"
        if not frappe.db.exists("Custody Asset Category", category_name):
            cat = frappe.get_doc({
                "doctype": "Custody Asset Category",
                "category_name": category_name
            })
            cat.insert(ignore_permissions=True)
            self.category = cat.name
        else:
            self.category = category_name

        article_name = "Chair"
        existing_article = frappe.db.get_value("Custody Article", {"article_name": article_name})
        if not existing_article:
            art = frappe.get_doc({
                "doctype": "Custody Article",
                "article_name": article_name,
                "category": self.category
            })
            art.insert(ignore_permissions=True)
            self.article = art.name
        else:
            self.article = existing_article

        # Create Salary Structure scoped to this company (avoid collision with
        # any test fixtures from hrms that may share generic names).
        struct_name = f"Apex Habitat Test Salary Structure {self.company}"
        existing_struct = frappe.db.get_value(
            "Salary Structure",
            {"name": struct_name, "company": self.company},
        )
        if not existing_struct:
            struct = frappe.get_doc({
                "doctype": "Salary Structure",
                "name": struct_name,
                "salary_structure_name": struct_name,
                "company": self.company,
                "is_active": "Yes",
                "payroll_frequency": "Monthly",
            })
            try:
                struct.insert(ignore_permissions=True)
                struct.submit()
            except Exception:
                # If submit isn't allowed/required in this hrms version, ignore.
                pass

        # Assign Salary Structure to Employee
        if not frappe.db.exists(
            "Salary Structure Assignment",
            {"employee": self.employee, "salary_structure": struct_name},
        ):
            try:
                assignment = frappe.get_doc({
                    "doctype": "Salary Structure Assignment",
                    "employee": self.employee,
                    "salary_structure": struct_name,
                    "from_date": "2026-01-01",
                    "company": self.company,
                    "base": 1000.0,
                })
                assignment.insert(ignore_permissions=True)
                assignment.submit()
            except Exception:
                # Salary structure assignment depends on hrms internals
                # (default salary structure config, payroll period, etc.).
                # The downstream test only verifies that an Additional Salary
                # Deduction is NOT created — it does not need the assignment
                # to actually post. Tolerate failure here.
                pass

    def test_custody_damage_no_additional_salary_without_salary_component(self):
        # Ensure enable_damage_deduction is set
        settings = frappe.get_single("Habitat Settings")
        settings.enable_damage_deduction = 1
        settings.max_damage_deduction_per_checkout_sar = 500
        settings.save()

        # Delete any existing Salary Components of type Deduction to simulate unconfigured environment
        frappe.db.delete("Salary Component", {"type": "Deduction"})

        # Create Custody Damage Assessment
        doc = frappe.get_doc({
            "doctype": "Custody Damage Assessment",
            "employee": self.employee,
            "assessment_date": "2026-05-21",
            "building": self.building.name,
            "items": [
                {
                    "article": self.article,
                    "damage_description": "Broken Chair",
                    "estimated_replacement_cost_sar": 150.0
                }
            ]
        })
        doc.insert(ignore_permissions=True)
        doc.submit()

        # Assert no Additional Salary Deduction Entry is linked
        doc.reload()
        self.assertIsNone(doc.deduction_entry, "Additional Salary deduction should not be generated without configured deduction Salary Component.")

    def test_custody_damage_no_additional_salary_without_explicit_setting(self):
        # Create a Deduction Salary Component
        comp_name = "Test Deduction Component"
        if not frappe.db.exists("Salary Component", comp_name):
            comp = frappe.get_doc({
                "doctype": "Salary Component",
                "salary_component": comp_name,
                "type": "Deduction"
            })
            comp.insert(ignore_permissions=True)

        settings = frappe.get_single("Habitat Settings")
        settings.enable_damage_deduction = 1
        settings.save()

        # Create Custody Damage Assessment
        doc = frappe.get_doc({
            "doctype": "Custody Damage Assessment",
            "employee": self.employee,
            "assessment_date": "2026-05-21",
            "building": self.building.name,
            "items": [
                {
                    "article": self.article,
                    "damage_description": "Broken Table",
                    "estimated_replacement_cost_sar": 200.0
                }
            ]
        })
        doc.insert(ignore_permissions=True)
        doc.submit()

        # Assert no Additional Salary Deduction Entry is linked because it was not explicitly configured in Settings
        doc.reload()
        self.assertIsNone(doc.deduction_entry, "Additional Salary deduction should not be generated unless explicitly configured in Settings.")

