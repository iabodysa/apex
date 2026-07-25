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

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from apex.apex_core.utils import employee_recovery
from apex.apex_core.utils.employee_recovery import bounded_installment, compute_recovery_installment


class _PolicyOff:
    """A Salary Deduction Policy with no Damage rule in force — the shipped
    default, expressed without writing to the Single (see
    test_the_shipped_policy_default_deducts_nothing for why that matters)."""

    global_max_percent_of_salary = 50.0
    default_salary_component = None

    def get_type_rule(self, rule_type):
        return None


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
    """The two "defer, post nothing" paths, against fixtures this class builds.

    Nothing here self-skips: an earlier version bailed out with ``skipTest`` when
    the site had no company / receivable account / active employee, which reported
    green while proving nothing. Every prerequisite is now created on demand.
    """

    def _company(self):
        existing = frappe.db.get_value("Company", {}, "name")
        if existing:
            return existing
        tag = frappe.generate_hash(length=12)
        return frappe.get_doc(
            {
                "doctype": "Company",
                "company_name": f"A102 Deferral {tag}",
                # Full hash, never a slice: a narrowed random identifier is what
                # apex/tests/test_fixture_identifier_entropy.py forbids, and a
                # colliding abbr is rejected by ERPNext's own uniqueness check.
                "abbr": f"AD{tag}",
                "default_currency": "SAR",
                "country": "Saudi Arabia",
            }
        ).insert(ignore_permissions=True).name

    def _receivable_account(self, company):
        """HRMS refuses to submit an advance on a non-Receivable account, so the
        account type — not merely the account — is the prerequisite."""
        existing = frappe.db.get_value(
            "Account",
            {"company": company, "account_type": "Receivable", "is_group": 0},
            "name",
        )
        if existing:
            return existing
        parent = frappe.db.get_value(
            "Account", {"company": company, "is_group": 1, "root_type": "Asset"}, "name"
        )
        self.assertTrue(parent, f"company {company} has no Asset group account")
        return frappe.get_doc(
            {
                "doctype": "Account",
                "account_name": f"A102 Advances {frappe.generate_hash(length=12)}",
                "company": company,
                "parent_account": parent,
                "root_type": "Asset",
                "account_type": "Receivable",
                "is_group": 0,
            }
        ).insert(ignore_permissions=True).name

    def _employee(self, company):
        return frappe.get_doc(
            {
                "doctype": "Employee",
                "first_name": f"A102 Deferral {frappe.generate_hash(length=12)}",
                "company": company,
                "status": "Active",
                "gender": "Male",
                "date_of_birth": "1990-01-01",
                "date_of_joining": "2020-01-01",
            }
        ).insert(ignore_permissions=True).name

    def _unpaid_advance(self):
        """A submitted Employee Advance the company has not paid out yet."""
        company = self._company()
        advance = frappe.get_doc(
            {
                "doctype": "Employee Advance",
                "employee": self._employee(company),
                "company": company,
                "purpose": f"A-102 deferral test {frappe.generate_hash(length=12)}",
                "advance_amount": 1000,
                "advance_account": self._receivable_account(company),
                "currency": frappe.db.get_value("Company", company, "default_currency"),
                "exchange_rate": 1,
                "repay_unclaimed_amount_from_salary": 1,
            }
        ).insert(ignore_permissions=True)
        advance.submit()
        return advance

    def test_the_shipped_policy_default_deducts_nothing(self):
        """[#a102po] The master switch ships OFF, so no wage is touched until the
        policy is activated after legal review.

        Read off a NEW policy document rather than the live Single: the policy is
        a Single, and saving one inside a test commits a mutation that escapes the
        suite's rollback and changes behaviour for every later test.
        """
        shipped = frappe.new_doc("Salary Deduction Policy")
        self.assertFalse(
            shipped.enable_salary_deductions,
            "salary deductions must ship disabled by default",
        )
        shipped.append(
            "type_rules",
            {"deduction_type": "Damage", "enabled": 1, "max_percent_of_salary": 10},
        )
        self.assertIsNone(
            shipped.get_type_rule("Damage"),
            "the master switch must gate every type rule, even an enabled one",
        )

        # [#a102nv] Non-vacuity: the same rule DOES come back once the master
        # switch is on, so the assertion above is about the switch, not about the
        # row being unreachable.
        shipped.enable_salary_deductions = 1
        self.assertIsNotNone(shipped.get_type_rule("Damage"))

    def test_nothing_is_recovered_while_the_policy_is_off(self):
        """[#a102po] With no Damage rule in force the engine recovers nothing —
        even from an advance the company HAS paid out.

        paid_amount is set deliberately: on an unpaid advance the engine returns
        0.0 for a different reason (nothing outstanding), which would make this
        assertion say nothing about the policy gate at all.
        """
        advance = self._unpaid_advance()
        frappe.db.set_value("Employee Advance", advance.name, "paid_amount", 1000)
        self.assertGreater(
            flt(frappe.db.get_value("Employee Advance", advance.name, "paid_amount")),
            0,
            "the fixture must have a real outstanding balance, or this proves nothing",
        )
        with patch.object(employee_recovery, "get_policy", return_value=_PolicyOff()):
            self.assertEqual(compute_recovery_installment(advance.name), 0.0)

    def test_nothing_is_recovered_before_the_company_has_paid(self):
        # [#a102pa] Outstanding is measured from paid_amount, which only the native
        # employee-advance payment entry sets — no disbursement, no deduction.
        advance = self._unpaid_advance()
        self.assertEqual(advance.paid_amount, 0)
        self.assertEqual(compute_recovery_installment(advance.name), 0.0)
