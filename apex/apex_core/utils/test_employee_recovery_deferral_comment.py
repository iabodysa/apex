# Copyright (c) 2026, afmcoltd

"""``schedule_recovery_deduction`` defers when no Salary Slip preview period can
be resolved for the employee — no active Salary Structure Assignment, in this
test. The outcome belongs on the Employee Advance the operator already has
open, not in a Python ``logger`` call floored at ERROR in production
(frappe/utils/logger.py:12).

The advance account is prepared through the app's OWN ``ensure_advance_account``
rather than by writing the Company field here. HRMS refuses an Employee Advance whose
company advance account is not of type Receivable, so a test that skips this step
errors on the fixture and never reaches the behaviour it asserts — and using the app's
setup path means this also fails if that path stops producing a Receivable account.
"""

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
        currency = frappe.db.get_value("Company", company, "default_currency") or "SAR"

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
