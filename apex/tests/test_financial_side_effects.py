# Copyright (c) 2026, AFMCO and contributors
# [#j03s5a]

import frappe
from frappe.utils import flt

from apex.tests.factories import ApexHabitatTestCase


def _configure_damage_policy(enabled=1, cap=500, salary_component=None, default_component=None, bypass_validate=False):
    """Set the Salary Deduction Policy Damage rule (the new home of the damage
    deduction config) and the global master switch. ``bypass_validate`` lets a test
    save an enabled-but-componentless rule (which the controller guard would normally
    reject) to exercise the controller's own missing-component path. Returns the doc."""
    policy = frappe.get_single("Salary Deduction Policy")
    policy.enable_salary_deductions = 1 if enabled else 0
    policy.global_max_percent_of_salary = 50
    policy.default_salary_component = default_component
    rule = next((r for r in policy.type_rules or [] if r.deduction_type == "Damage"), None)
    if rule is None:
        rule = policy.append("type_rules", {"deduction_type": "Damage"})
    rule.enabled = 1 if enabled else 0
    rule.cap_amount_per_event = cap
    rule.salary_component = salary_component
    if bypass_validate:
        policy.flags.ignore_validate = True
    policy.save(ignore_permissions=True)
    return policy


class TestFinancialSideEffects(ApexHabitatTestCase):
    def setUp(self):
        # [#2uh11u]
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

        # Reuse only an employee whose joining date is on/before the salary
        # assignment's from_date (2026-01-01); a foreign test employee that joined
        # "today" would make the hardcoded assignment fail (joining-after-from_date),
        # so fall through and provision our own with a safe joining date.
        joined_filter = ["<=", "2026-01-01"]
        self.employee = frappe.db.get_value(
            "Employee", {"company": self.company, "date_of_joining": joined_filter}
        )
        if not self.employee:
            self.employee = frappe.db.get_value("Employee", {"date_of_joining": joined_filter})
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

        # [#gbrgot]
        site_name = "Test Financial Site"
        if not frappe.db.exists("Site", site_name):
            self.site = frappe.get_doc({
                "doctype": "Site",
                "site_name": site_name
            })
            self.site.insert(ignore_permissions=True)
        else:
            self.site = frappe.get_doc("Site", site_name)

        building_name = "Test Financial Building"
        if not frappe.db.exists("Building", building_name):
            self.building = frappe.get_doc({
                "doctype": "Building",
                "building_name": building_name,
                "site": self.site.name,
                "total_capacity": 10
            })
            self.building.insert(ignore_permissions=True)
        else:
            self.building = frappe.get_doc("Building", building_name)

        # [#ryfpzi]
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

        # [#9ztpd7] A submitted Salary Structure Assignment is the precondition
        # HRMS's Additional Salary checks on submit (validate_salary_structure); a
        # bare site has none, so build one here. Everything is bound to the
        # EMPLOYEE's own company (not self.company, which can differ across test
        # classes on a shared site) so the assignment's company == structure's
        # company == employee's company and HRMS validate_company holds. The
        # structure carries one Earning (required to submit) and no tax component
        # (so no Income Tax Slab is demanded); from_date precedes any test
        # payroll_date.
        emp_company = frappe.db.get_value("Employee", self.employee, "company")

        earn_component = "Apex Habitat Test Earning"
        if not frappe.db.exists("Salary Component", earn_component):
            frappe.get_doc({
                "doctype": "Salary Component",
                "salary_component": earn_component,
                "type": "Earning",
            }).insert(ignore_permissions=True)

        struct_name = f"Apex Habitat Test Salary Structure {emp_company}"
        if not frappe.db.get_value(
            "Salary Structure", {"name": struct_name, "company": emp_company, "docstatus": 1}
        ):
            struct = frappe.get_doc({
                "doctype": "Salary Structure",
                "name": struct_name,
                "salary_structure_name": struct_name,
                "company": emp_company,
                "currency": "SAR",
                "is_active": "Yes",
                "payroll_frequency": "Monthly",
                "earnings": [{"salary_component": earn_component, "amount": 1000.0}],
            })
            struct.insert(ignore_permissions=True)
            struct.submit()

        has_assignment = frappe.db.exists(
            "Salary Structure Assignment",
            {"employee": self.employee, "salary_structure": struct_name, "docstatus": 1},
        )
        if not has_assignment:
            assignment = frappe.get_doc({
                "doctype": "Salary Structure Assignment",
                "employee": self.employee,
                "salary_structure": struct_name,
                "from_date": "2026-01-01",
                "company": emp_company,
                "currency": "SAR",
                "base": 1000.0,
            })
            assignment.insert(ignore_permissions=True)
            assignment.submit()

    def test_custody_damage_no_additional_salary_without_salary_component(self):
        # [#t393jb]
        # [#b0j60b]
        frappe.db.delete("Salary Component", {"type": "Deduction"})
        # enabled rule, no component (and no default) -> controller skips, no entry.
        # bypass_validate because the Policy guard would normally reject saving an
        # enabled rule with no component; here we exercise the controller's own guard.
        _configure_damage_policy(enabled=1, cap=500, salary_component=None, bypass_validate=True)

        # [#cvlsab]
        doc = frappe.get_doc({
            "doctype": "Custody Damage Assessment",
            "employee": self.employee,
            "assessment_date": "2026-05-21",
            "building": self.building.name,
            "items": [
                {
                    "article": self.article,
                    "damage_description": "Broken Chair",
                    "estimated_replacement_cost": 150.0
                }
            ]
        })
        doc.insert(ignore_permissions=True)
        doc.submit()

        # [#4bu0gp]
        doc.reload()
        self.assertIsNone(doc.deduction_entry, "Additional Salary deduction should not be generated without configured deduction Salary Component.")

    def test_damage_deduction_back_propagates_to_source_checkout(self):
        # back-link from the assessment to its checkout must post the deduction
        # (Additional Salary + amount) onto the checkout's Financials tab
        comp_name = "Test Deduction Component"
        if not frappe.db.exists("Salary Component", comp_name):
            frappe.get_doc({
                "doctype": "Salary Component",
                "salary_component": comp_name,
                "type": "Deduction",
            }).insert(ignore_permissions=True)

        _configure_damage_policy(enabled=1, cap=500, salary_component=comp_name)

        # draft checkout is the back-write target; QA assignment + ignore_links
        # keeps validate's early-return path (no full assignment chain needed)
        checkout = frappe.get_doc({
            "doctype": "Housing Checkout",
            "naming_series": "ACC-CHKOUT-.YYYY.-.####",
            "assignment": "ACC-ASGN-QA",
            "checkout_date": "2026-05-21",
            "checkout_reason": "End of Contract",
            "employee": self.employee,
        })
        checkout.insert(ignore_permissions=True, ignore_links=True)

        assessment = frappe.get_doc({
            "doctype": "Custody Damage Assessment",
            "employee": self.employee,
            "assessment_date": "2026-05-21",
            "building": self.building.name,
            "source_checkout": checkout.name,
            "items": [
                {
                    "article": self.article,
                    "damage_description": "Broken Chair",
                    "estimated_replacement_cost": 175.0,
                }
            ],
        })
        assessment.insert(ignore_permissions=True)
        assessment.submit()
        assessment.reload()

        self.assertTrue(
            assessment.deduction_entry,
            "Additional Salary deduction should be generated when fully configured.",
        )

        checkout.reload()
        self.assertEqual(
            checkout.additional_salary_deduction,
            assessment.deduction_entry,
            "Checkout must link the Additional Salary posted by its damage assessment.",
        )
        self.assertEqual(
            flt(checkout.damage_deduction_amount),
            175.0,
            "Checkout must reflect the posted damage deduction amount.",
        )

        frappe.delete_doc("Housing Checkout", checkout.name, force=True, ignore_permissions=True)

    def test_custody_damage_no_additional_salary_without_explicit_setting(self):
        # [#paxi0y]
        comp_name = "Test Deduction Component"
        if not frappe.db.exists("Salary Component", comp_name):
            comp = frappe.get_doc({
                "doctype": "Salary Component",
                "salary_component": comp_name,
                "type": "Deduction"
            })
            comp.insert(ignore_permissions=True)

        # gate enabled, but the rule names no component (and no default) -> no entry,
        # even though a deduction component exists in HRMS but is not wired to the rule
        _configure_damage_policy(enabled=1, cap=500, salary_component=None, bypass_validate=True)

        # [#cvlsab]
        doc = frappe.get_doc({
            "doctype": "Custody Damage Assessment",
            "employee": self.employee,
            "assessment_date": "2026-05-21",
            "building": self.building.name,
            "items": [
                {
                    "article": self.article,
                    "damage_description": "Broken Table",
                    "estimated_replacement_cost": 200.0
                }
            ]
        })
        doc.insert(ignore_permissions=True)
        doc.submit()

        # [#rrubmw]
        doc.reload()
        self.assertIsNone(doc.deduction_entry, "Additional Salary deduction should not be generated unless a component is wired to the Policy Damage rule.")

