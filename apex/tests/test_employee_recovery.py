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

Run standalone:
    bench --site <site> run-tests --module apex.tests.test_employee_recovery
"""

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_months, today

from apex.apex_core.utils import employee_recovery
from apex.apex_core.utils.employee_recovery import bounded_installment, compute_recovery_installment
from apex.tests import factories

# [#8evoal]
test_ignore = [
    "Additional Salary",
    "Company",
    "Cost Center",
    "Currency",
    "Employee",
    "Payment Entry",
    "Role",
    "Salary Component",
    "User",
]


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
    """The two "defer, post nothing" gates, proved against a payroll chain this
    class builds itself.

    Every fixture — company, Receivable account, Employee, Salary Component,
    Salary Structure + Assignment — is built in ``setUpClass``. It used to
    ``skipTest`` unless the site happened to already carry an Active Employee,
    which nothing in ``tests/before_tests.py`` provisions: on a fresh CI site the
    whole class vanished and reported success, and on a dirty one it silently
    recovered from another test's worker.

    Three rules keep it order-independent, so running it alone on a bare site is
    the same run as running it last (A-140):

      * nothing is borrowed. The Employee and the wage are private to this class,
        so no other test can supply or consume them.
      * the Salary Deduction Policy is a Single, so it is mocked at the module
        seam rather than saved. ``FrappeTestCase`` rolls back only at CLASS
        teardown while every later class's ``setUpClass`` commits, so a saved
        Single mutation escapes the rollback and disables deductions for the rest
        of the suite.
      * each test gets its OWN pay period (``setUp`` walks the payroll date
        forward three months per test), so one test's advance can never consume
        another's payroll availability.
    """

    # The worker's monthly wage in the fixture chain, and the Damage rule's cap.
    # Every expected number below is derived from them rather than hard-coded.
    WAGE = 6000.0
    CAP_PERCENT = 10.0
    CAPPED_INSTALLMENT = WAGE * CAP_PERCENT / 100.0
    # What the company raises, and (once disbursed) still has outstanding. Comfortably
    # above the capped installment, so the cap is what binds and not the balance.
    ADVANCE = 5000.0

    # Walked forward in setUp so no two tests share a payroll month.
    _period_offset = 0

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.company = factories.ensure_company()
        cls.currency = frappe.db.get_value("Company", cls.company, "default_currency") or "SAR"
        # HRMS refuses to submit an Employee Advance on a non-Receivable account.
        cls.advance_account = factories.ensure_account(cls.company, "Receivable", "Asset")
        cls.employee = factories.make_payroll_employee(cls.company)
        cls.deduction_component = factories.make_salary_component("Deduction")
        factories.assign_monthly_wage(cls.employee, cls.company, cls.WAGE, cls.currency)

    def setUp(self):
        frappe.set_user("Administrator")
        type(self)._period_offset += 3
        self.payroll_date = add_months(today(), type(self)._period_offset)

    def _advance(self, paid=0.0, amount=ADVANCE):
        """A submitted Employee Advance for this class's worker.

        ``paid`` stands in for the disbursement: only HRMS's own employee-advance
        payment entry sets ``paid_amount``, and the engine measures outstanding
        from it, so a fixture that skipped it could never reach the cap logic.
        """
        advance = frappe.get_doc(
            {
                "doctype": "Employee Advance",
                "employee": self.employee,
                "company": self.company,
                "posting_date": today(),
                "purpose": f"A-102 deferral fixture {factories.fixture_tag()}",
                "advance_amount": amount,
                "advance_account": self.advance_account,
                "currency": self.currency,
                "exchange_rate": 1,
                "repay_unclaimed_amount_from_salary": 1,
            }
        ).insert(ignore_permissions=True)
        advance.submit()
        if paid:
            frappe.db.set_value("Employee Advance", advance.name, "paid_amount", paid)
        return advance

    def _policy(self, enabled):
        """The REAL Salary Deduction Policy Single with its master switch set in
        memory only, patched in at the module seam.

        The gate under test (master switch AND the row's own ``enabled`` flag) is
        still ``SalaryDeductionPolicy.get_type_rule``'s own code — only the
        persistence is avoided, because a saved Single poisons the whole suite.
        """
        policy = frappe.get_single("Salary Deduction Policy")
        policy.enable_salary_deductions = 1 if enabled else 0
        policy.global_max_percent_of_salary = 50.0
        policy.set("type_rules", [])
        policy.append(
            "type_rules",
            {
                "deduction_type": "Damage",
                "enabled": 1,
                "salary_component": self.deduction_component,
                "max_percent_of_salary": self.CAP_PERCENT,
            },
        )
        return patch.object(employee_recovery, "get_policy", return_value=policy)

    def test_nothing_is_recovered_while_the_policy_is_off(self):
        # [#a102po] The shipped default: master switch off, so no wage is ever touched.
        advance = self._advance(paid=self.ADVANCE)
        with self._policy(enabled=False):
            self.assertEqual(
                compute_recovery_installment(advance.name, self.payroll_date),
                0.0,
                "the master switch being off must defer the whole recovery",
            )

        # [#a140nv] Non-vacuity: the SAME advance in the SAME pay period, with only
        # the master switch flipped on, does recover. Without this the zero above is
        # satisfied just as well by an unpaid advance or an unknown wage, and the
        # policy gate is never the thing being proved.
        with self._policy(enabled=True):
            self.assertEqual(
                compute_recovery_installment(advance.name, self.payroll_date),
                self.CAPPED_INSTALLMENT,
            )

    def test_nothing_is_recovered_before_the_company_has_paid(self):
        # [#a102pa] Outstanding is measured from paid_amount, which only the native
        # employee-advance payment entry sets — no disbursement, no deduction.
        advance = self._advance()
        self.assertEqual(advance.paid_amount, 0)
        with self._policy(enabled=True):
            self.assertEqual(
                compute_recovery_installment(advance.name, self.payroll_date),
                0.0,
                "money the company never disbursed must never be deducted from a wage",
            )

            # [#a140nv] Non-vacuity: the disbursement was the ONLY thing missing.
            # Recording it against the same advance, with the policy untouched,
            # turns the same call into a real installment.
            frappe.db.set_value("Employee Advance", advance.name, "paid_amount", self.ADVANCE)
            self.assertEqual(
                compute_recovery_installment(advance.name, self.payroll_date),
                self.CAPPED_INSTALLMENT,
            )
