# Copyright (c) 2026, afmcoltd


import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today

from apex.apex_core.setup.employee_advance_recovery import ensure_advance_account
from apex.apex_core.utils.employee_recovery import schedule_recovery_deduction
from apex.tests.factories import ensure_company, make_employee


class TestScheduleRecoveryDeductionCommentsOnTheAdvance(FrappeTestCase):
    def setUp(self):
        self._enabled = frappe.db.get_single_value(
            "Salis Settings", "enable_employee_advance_recovery"
        )
        frappe.db.set_single_value("Salis Settings", "enable_employee_advance_recovery", 1)

    def tearDown(self):
        frappe.db.set_single_value(
            "Salis Settings", "enable_employee_advance_recovery", self._enabled
        )

    def test_no_salary_structure_assignment_comments_on_the_advance(self):
        company = ensure_company()
        ensure_advance_account(company)
        employee = make_employee(name="Apex Recovery Test Employee", company=company)
        employee_name = employee.name if hasattr(employee, "name") else employee["name"]
        currency = frappe.db.get_value("Company", company, "default_currency")

        advance = frappe.get_doc(
            {
                "doctype": "Employee Advance",
                "naming_series": "HR-EAD-.YYYY.-",
                "employee": employee_name,
                "company": company,
                "currency": currency,
                "exchange_rate": 1,
                "purpose": "Apex regression test",
                "advance_amount": 100,
                "posting_date": today(),
            }
        )
        advance.insert(ignore_permissions=True)

        before = frappe.db.count(
            "Comment",
            {"reference_doctype": "Employee Advance", "reference_name": advance.name},
        )

        result = schedule_recovery_deduction(advance.name)

        after = frappe.db.count(
            "Comment",
            {"reference_doctype": "Employee Advance", "reference_name": advance.name},
        )
        self.assertIsNone(result)
        self.assertGreater(after, before)
