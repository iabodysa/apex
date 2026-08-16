# Copyright (c) 2026, AFMCO and contributors
"""The advance ACCOUNT half of the native employee cost-recovery engine.

Cut from 621 lines to what is here, and the reason is worth reading
before adding to it. Thirteen of its fifteen cases had been ERRORING on every run
against an API that no longer exists — they patched ``employee_recovery.get_policy``
and called ``_recovery_component(policy)``, but the engine moved off the
``Salary Deduction Policy`` Single (that DocType is deleted outright by
``apex/patches/v2_6/converge_native_support_and_recovery.py:174-176``) and
``_recovery_component()`` now takes no arguments. Nothing reported it, because
``.claude/`` is gitignored and CI has never run this directory.

Every one of those thirteen contracts is covered — and actually RUN — by the tracked
``apex/apex_core/utils/test_employee_recovery.py``:

  source-link + native draft factory  -> ::test_scheduler_locks_advance_and_uses_native_draft_factory
  a pending draft is counted once     -> ::test_existing_draft_installment_defers_cleared_balance
  the installment lands in its period -> ::test_weekly_preview_dates_bound_draft_headroom_to_that_pay_period
  a second run queues nothing         -> ::test_existing_draft_or_submitted_installment_is_not_duplicated
  a committed period defers recovery  -> ::test_recovery_defers_when_native_preview_has_no_remaining_headroom
  submit/cancel move the balance      -> ::test_native_additional_salary_submit_and_cancel_reverse_advance
  component-type refusal              -> ::test_before_submit_rejects_mismatched_recovery_contract_before_native_mutation
  nothing scheduled when disabled     -> ::test_unpaid_advance_defers_recovery

What is kept is the pair that suite does NOT have: ``raise_recovery_advance`` driven
against a REAL Chart of Accounts. The tracked suite only mocks the account type
(test_employee_recovery.py:314-317), so nothing else in the app proves that HRMS accepts
the advance on a genuine Receivable account, or that a misconfigured non-Receivable
default degrades to "no recovery raised" instead of throwing and blocking the
operational document.

Every fixture is built by this file (company, receivable account, employee): there is no
``skipTest`` anywhere, so a green here is never a hollow green on a bare site.

Run standalone:
    python .claude/tests/run_suite.py --site <site> \
        --pattern apex.apex_core.utils.test_employee_recovery_installments
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.apex_core.utils.employee_recovery import raise_recovery_advance

test_ignore = [
    "Company",
    "Cost Center",
    "Currency",
    "Employee",
    "Payment Entry",
    "Role",
    "User",
]


def _tag():
    """A collision-free fixture suffix (>=12 random characters — see
    apex/tests/test_fixture_identifier_entropy.py)."""
    return frappe.generate_hash(length=12)


class TestRecoveryAdvanceAccount(FrappeTestCase):
    """One shared company and chart; a fresh employee per case."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.tag = _tag()
        cls.company = cls._company()
        cls.currency = frappe.db.get_value("Company", cls.company, "default_currency") or "SAR"
        cls.advance_account = cls._receivable_account(cls.company)

    def setUp(self):
        frappe.set_user("Administrator")

    @classmethod
    def _company(cls):
        existing = frappe.db.get_value("Company", {}, "name")
        if existing:
            return existing
        return frappe.get_doc(
            {
                "doctype": "Company",
                "company_name": f"A102 Recovery {cls.tag}",
                # Full hash, never a slice: a narrowed random identifier is what
                # apex/tests/test_fixture_identifier_entropy.py forbids.
                "abbr": f"A1{cls.tag}",
                "default_currency": "SAR",
                "country": "Saudi Arabia",
            }
        ).insert(ignore_permissions=True).name

    @classmethod
    def _receivable_account(cls, company):
        """A non-group Receivable account, created when the chart has none.

        HRMS refuses to submit an Employee Advance whose advance account is not
        Receivable, so this account type is what the whole chain depends on.
        """
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
        assert parent, f"company {company} has no Asset group account to hang a Receivable under"
        return frappe.get_doc(
            {
                "doctype": "Account",
                "account_name": f"A102 Employee Advances {cls.tag}",
                "company": company,
                "parent_account": parent,
                "root_type": "Asset",
                "account_type": "Receivable",
                "is_group": 0,
            }
        ).insert(ignore_permissions=True).name

    @classmethod
    def _employee(cls, company):
        return frappe.get_doc(
            {
                "doctype": "Employee",
                "first_name": f"A102 Recovery {_tag()}",
                "company": company,
                "status": "Active",
                "gender": "Male",
                "date_of_birth": "1990-01-01",
                "date_of_joining": "2020-01-01",
            }
        ).insert(ignore_permissions=True).name

    def _restore_company_advance_account(self, previous):
        frappe.db.set_value(
            "Company", self.company, "default_employee_advance_account", previous
        )

    def test_the_advance_uses_the_company_default_employee_advance_account(self):
        """The receivable lands on the company's configured advance account —
        one account, read from the Company, never chosen by apex."""
        previous = frappe.db.get_value(
            "Company", self.company, "default_employee_advance_account"
        )
        self.addCleanup(self._restore_company_advance_account, previous)
        frappe.db.set_value(
            "Company", self.company, "default_employee_advance_account", self.advance_account
        )

        subject = self._employee(self.company)
        name = raise_recovery_advance(
            source_doctype="Employee",
            source_name=subject,
            employee=subject,
            amount=750,
            purpose=f"A-102 account consistency {_tag()}",
        )
        self.assertTrue(
            name,
            "a company with a Receivable Employee Advance Account must raise the advance",
        )
        row = frappe.db.get_value(
            "Employee Advance",
            name,
            [
                "advance_account",
                "docstatus",
                "repay_unclaimed_amount_from_salary",
                "custom_source_doctype",
                "custom_source_document",
            ],
            as_dict=True,
        )
        self.assertEqual(row.advance_account, self.advance_account)
        self.assertEqual(row.docstatus, 1)
        self.assertEqual(
            row.repay_unclaimed_amount_from_salary,
            1,
            "the advance must be marked as recovered from salary, or HRMS's own "
            "return-through-Additional-Salary path never applies",
        )
        self.assertEqual(row.custom_source_doctype, "Employee")
        self.assertEqual(row.custom_source_document, subject)
        self.assertEqual(
            frappe.db.get_value("Account", row.advance_account, "account_type"),
            "Receivable",
            "HRMS refuses to submit an advance on a non-Receivable account",
        )

    def test_an_advance_account_that_is_not_receivable_raises_nothing(self):
        """A misconfigured account degrades to 'no recovery raised' instead of
        blocking the operational document."""
        previous = frappe.db.get_value(
            "Company", self.company, "default_employee_advance_account"
        )
        self.addCleanup(self._restore_company_advance_account, previous)

        payable = frappe.db.get_value(
            "Account",
            {"company": self.company, "account_type": "Payable", "is_group": 0},
            "name",
        )
        if not payable:
            parent = frappe.db.get_value(
                "Account",
                {"company": self.company, "is_group": 1, "root_type": "Liability"},
                "name",
            )
            self.assertTrue(parent, "company has no Liability group account to hang a Payable under")
            payable = frappe.get_doc(
                {
                    "doctype": "Account",
                    "account_name": f"A102 Not Receivable {_tag()}",
                    "company": self.company,
                    "parent_account": parent,
                    "root_type": "Liability",
                    "account_type": "Payable",
                    "is_group": 0,
                }
            ).insert(ignore_permissions=True).name

        frappe.db.set_value(
            "Company", self.company, "default_employee_advance_account", payable
        )
        subject = self._employee(self.company)
        self.assertIsNone(
            raise_recovery_advance(
                source_doctype="Employee",
                source_name=subject,
                employee=subject,
                amount=500,
                purpose=f"non-receivable advance account {_tag()}",
            ),
            "a non-Receivable advance account must raise nothing, and must not throw",
        )
        self.assertEqual(
            frappe.db.count(
                "Employee Advance",
                {"custom_source_doctype": "Employee", "custom_source_document": subject},
            ),
            0,
        )
