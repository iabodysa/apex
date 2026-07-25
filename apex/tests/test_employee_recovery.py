# Copyright (c) 2026, AFMCO and contributors
"""Employee cost-recovery engine tests (A-102).

Two layers:

  * ``bounded_installment`` is pure arithmetic, so the KSA-cap rule that decides how
    much of a wage a recovery may take is proved outright — every limit is shown to
    bind, and a zero limit is shown to defer the whole recovery rather than post a
    negative or an uncapped deduction.
  * the two "defer, post nothing" paths that must hold on any site: the Salary
    Deduction Policy being off (the shipped default), and an advance the company has
    not actually paid out yet.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.apex_core.utils.employee_recovery import bounded_installment, compute_recovery_installment


class TestBoundedInstallment(FrappeTestCase):
    def test_outstanding_binds(self):
        # [#a102b1] Never recover more than is still owed.
        self.assertEqual(bounded_installment(200, 5000, 5000, 1000), 200)

    def test_statutory_cap_binds(self):
        # [#a102b2] The KSA max-%-of-wage ceiling wins over a bigger balance.
        self.assertEqual(bounded_installment(9000, 500, 5000, 1000), 500)

    def test_payroll_availability_binds(self):
        # [#a102b3] What the pay period can still bear wins over the cap.
        self.assertEqual(bounded_installment(9000, 5000, 300, 1000), 300)

    def test_agreed_installment_binds(self):
        self.assertEqual(bounded_installment(9000, 5000, 5000, 750), 750)

    def test_no_agreed_installment_is_not_a_zero_limit(self):
        # [#a102b4] Blank "agreed installment" means unconstrained, not "recover nothing".
        self.assertEqual(bounded_installment(9000, 5000, 4000, 0), 4000)

    def test_zero_availability_defers_the_whole_recovery(self):
        self.assertEqual(bounded_installment(9000, 5000, 0, 1000), 0.0)

    def test_over_committed_pay_period_never_returns_a_negative(self):
        # [#a102b5] Net pay can never be pushed below zero by a recovery.
        self.assertEqual(bounded_installment(9000, 5000, -1200, 1000), 0.0)

    def test_cleared_balance_recovers_nothing(self):
        self.assertEqual(bounded_installment(0, 5000, 5000, 1000), 0.0)


class TestRecoveryDeferralPaths(FrappeTestCase):
    def _unpaid_advance(self):
        """A submitted Employee Advance the company has not paid out yet."""
        company = frappe.db.get_value("Company", {}, "name")
        receivable = frappe.db.get_value(
            "Account", {"company": company, "account_type": "Receivable", "is_group": 0}, "name"
        )
        employee = frappe.db.get_value("Employee", {"status": "Active", "company": company})
        if not (company and receivable and employee):
            self.skipTest("site has no company / receivable account / active employee")
        advance = frappe.get_doc(
            {
                "doctype": "Employee Advance",
                "employee": employee,
                "company": company,
                "purpose": "A-102 deferral test",
                "advance_amount": 1000,
                "advance_account": receivable,
                "currency": frappe.db.get_value("Company", company, "default_currency"),
                "exchange_rate": 1,
                "repay_unclaimed_amount_from_salary": 1,
            }
        ).insert(ignore_permissions=True)
        advance.submit()
        return advance

    def test_nothing_is_recovered_while_the_policy_is_off(self):
        # [#a102po] The shipped default: master switch off, so no wage is ever touched.
        policy = frappe.get_single("Salary Deduction Policy")
        policy.enable_salary_deductions = 0
        policy.save(ignore_permissions=True)
        advance = self._unpaid_advance()
        self.assertEqual(compute_recovery_installment(advance.name), 0.0)

    def test_nothing_is_recovered_before_the_company_has_paid(self):
        # [#a102pa] Outstanding is measured from paid_amount, which only the native
        # employee-advance payment entry sets — no disbursement, no deduction.
        advance = self._unpaid_advance()
        self.assertEqual(advance.paid_amount, 0)
        self.assertEqual(compute_recovery_installment(advance.name), 0.0)
