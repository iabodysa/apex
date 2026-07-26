# Copyright (c) 2026, AFMCO and contributors
"""Wage-installment side of the native employee cost-recovery engine (A-102).

The sibling ``test_employee_recovery.py`` proves the pure cap
arithmetic; this file proves what happens against a real payroll chain:

  * an installment is SOURCE-LINKED to its Employee Advance through the native
    ``ref_doctype`` / ``ref_docname`` pair and is DUPLICATE-SAFE (one per advance
    per pay period, counting drafts);
  * the Salary Component and the advance account are checked for consistency
    before anything is posted;
  * submitting the installment UPDATES the recovered balance and cancelling it
    REVERSES it — natively, through HRMS's own
    ``AdditionalSalary.update_return_amount_in_employee_advance``, which apex
    never reimplements.

Every fixture is built by this file (company, receivable account, employee,
salary component, salary structure, structure assignment, advance): there is no
``skipTest`` anywhere, so a green here is never a hollow green on a bare site.

Two isolation rules make the class order-independent:

  * the Salary Deduction Policy is a Single, so it is mocked at the module seam
    rather than saved — a committed Single mutation escapes the suite's rollback
    and poisons every later test on the site;
  * every test gets its OWN pay period (``setUp`` walks the payroll date forward
    three months per test), so one test's queued installment can never consume
    another test's payroll availability.

Run standalone:
    bench --site <site> run-tests \
        --module apex.apex_core.utils.test_employee_recovery_installments
"""

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_months, flt, get_first_day, get_last_day, today

from apex.apex_core.utils import employee_recovery
from apex.apex_core.utils.employee_recovery import (
    _pending_installments,
    _recovery_component,
    compute_recovery_installment,
    raise_recovery_advance,
    schedule_recovery_deduction,
)

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

# The worker's monthly wage in the fixture chain. Every expected number below is
# derived from it, so the assertions are arithmetic rather than magic constants.
WAGE = 6000.0
# Damage rule cap: 10% of wage = 600.00 per pay period (well under the KSA 50%).
CAP_PERCENT = 10.0
CAPPED_INSTALLMENT = WAGE * CAP_PERCENT / 100.0


def _tag():
    """A collision-free fixture suffix (>=12 random characters — see
    apex/tests/test_fixture_identifier_entropy.py)."""
    return frappe.generate_hash(length=12)


class _StubPolicy:
    """Stands in for the Salary Deduction Policy Single.

    The policy is a Single: saving it inside a test commits a mutation that
    escapes the suite's rollback and changes behaviour for every later test. The
    engine only ever asks it two questions, so answering them directly keeps each
    test hermetic and leaves the shipped default (deductions OFF) untouched.
    """

    def __init__(self, salary_component=None, cap_percent=CAP_PERCENT, rule=True):
        self.global_max_percent_of_salary = 50.0
        self.default_salary_component = None
        self._rule = (
            frappe._dict(
                deduction_type="Damage",
                enabled=1,
                salary_component=salary_component,
                max_percent_of_salary=cap_percent,
            )
            if rule
            else None
        )

    def get_type_rule(self, rule_type):
        return self._rule if rule_type == "Damage" else None


class TestEmployeeRecoveryInstallments(FrappeTestCase):
    """One shared payroll chain; a fresh advance and a private pay period per test."""

    # Walked forward in setUp so no two tests share a payroll month.
    _period_offset = 0

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.tag = _tag()
        cls.company = cls._company()
        cls.currency = frappe.db.get_value("Company", cls.company, "default_currency") or "SAR"
        cls.advance_account = cls._receivable_account(cls.company)
        cls.employee = cls._employee(cls.company)
        cls.deduction_component = cls._salary_component("Deduction")
        cls.earning_component = cls._salary_component("Earning")
        cls._assign_salary_structure()

    def setUp(self):
        frappe.set_user("Administrator")
        type(self)._period_offset += 3
        self.payroll_date = add_months(today(), type(self)._period_offset)
        # Pin the company default to this class's Receivable account. Without it the
        # chain inherits whatever the site already had, and a long-lived bench whose
        # default advance account is not Receivable fails every test here on an HRMS
        # validation that has nothing to do with what is under test. A test that only
        # passes on a site seeded a particular way is proving the seed, not the code.
        previous = frappe.db.get_value(
            "Company", self.company, "default_employee_advance_account"
        )
        self.addCleanup(self._restore_company_advance_account, previous)
        frappe.db.set_value(
            "Company", self.company, "default_employee_advance_account", self.advance_account
        )

    # Fixtures below build the smallest HRMS chain each clause needs.

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

    @classmethod
    def _salary_component(cls, component_type):
        name = f"A102 {component_type} {cls.tag}"
        return frappe.get_doc(
            {
                "doctype": "Salary Component",
                "salary_component": name,
                "salary_component_abbr": f"A{component_type[0]}{cls.tag}",
                "type": component_type,
            }
        ).insert(ignore_permissions=True).name

    @classmethod
    def _assign_salary_structure(cls):
        """A submitted Salary Structure Assignment is what gives the worker a
        known monthly wage — ``_monthly_wage`` reads its ``base``, and HRMS
        refuses to submit an Additional Salary without one."""
        structure = frappe.get_doc(
            {
                "doctype": "Salary Structure",
                "name": f"A102 Structure {cls.tag}",
                "company": cls.company,
                "is_active": "Yes",
                "currency": cls.currency,
                "payroll_frequency": "Monthly",
                "earnings": [
                    {
                        "doctype": "Salary Detail",
                        "salary_component": cls.earning_component,
                        "amount": WAGE,
                        "parentfield": "earnings",
                    }
                ],
            }
        ).insert(ignore_permissions=True)
        structure.submit()
        cls.salary_structure = structure.name

        assignment = frappe.get_doc(
            {
                "doctype": "Salary Structure Assignment",
                "employee": cls.employee,
                "salary_structure": cls.salary_structure,
                "company": cls.company,
                "currency": cls.currency,
                "from_date": "2020-01-01",
                "base": WAGE,
            }
        ).insert(ignore_permissions=True)
        assignment.submit()

    def _advance(self, paid=2000.0, amount=5000.0):
        """A submitted Employee Advance the company HAS paid out, so there is a
        real outstanding balance to recover."""
        advance = frappe.get_doc(
            {
                "doctype": "Employee Advance",
                "employee": self.employee,
                "company": self.company,
                "posting_date": today(),
                "purpose": f"A-102 installment fixture {_tag()}",
                "advance_amount": amount,
                "advance_account": self.advance_account,
                "currency": self.currency,
                "exchange_rate": 1,
                "repay_unclaimed_amount_from_salary": 1,
            }
        ).insert(ignore_permissions=True)
        advance.submit()
        # Only the native payment entry sets paid_amount, and the engine measures
        # outstanding from it, so the fixture stands in for that disbursement.
        frappe.db.set_value("Employee Advance", advance.name, "paid_amount", paid)
        return advance.name

    def _policy(self, **kwargs):
        kwargs.setdefault("salary_component", self.deduction_component)
        return patch.object(
            employee_recovery, "get_policy", return_value=_StubPolicy(**kwargs)
        )

    def _return_amount(self, advance):
        return flt(frappe.db.get_value("Employee Advance", advance, "return_amount"))

    def _installment_count(self, advance):
        return frappe.db.count(
            "Additional Salary", {"ref_doctype": "Employee Advance", "ref_docname": advance}
        )

    # Clause: a deduction has to trace back to the advance it repays.

    def test_the_installment_carries_the_native_link_back_to_its_advance(self):
        """``ref_doctype`` / ``ref_docname`` are the exact keys HRMS's own
        ``update_return_amount_in_employee_advance`` reads. Asserted by reading
        the row back out of the database, not off the returned object."""
        advance = self._advance()
        with self._policy():
            installment = schedule_recovery_deduction(advance, self.payroll_date)
        self.assertTrue(installment, "a recoverable advance must queue one installment")

        row = frappe.db.get_value(
            "Additional Salary",
            installment,
            [
                "ref_doctype",
                "ref_docname",
                "employee",
                "salary_component",
                "type",
                "amount",
                "docstatus",
                "overwrite_salary_structure_amount",
            ],
            as_dict=True,
        )
        self.assertEqual(row.ref_doctype, "Employee Advance")
        self.assertEqual(row.ref_docname, advance)
        self.assertEqual(row.employee, self.employee)
        self.assertEqual(row.salary_component, self.deduction_component)
        self.assertEqual(row.type, "Deduction", "an installment must reduce the wage, never add to it")
        self.assertEqual(flt(row.amount), CAPPED_INSTALLMENT)
        self.assertEqual(row.docstatus, 0, "payroll keeps the final say — the row stays a draft")
        self.assertEqual(
            row.overwrite_salary_structure_amount,
            0,
            "an installment ADDS a deduction; it must never overwrite a structure row",
        )

    def test_a_pending_installment_is_counted_only_against_its_own_advance(self):
        """Non-vacuity for the source link: a draft queued against a DIFFERENT
        advance must not reduce this one's outstanding balance."""
        advance = self._advance()
        other = self._advance()
        with self._policy():
            self.assertTrue(schedule_recovery_deduction(other, self.payroll_date))

        self.assertEqual(_pending_installments(advance), 0.0)
        self.assertEqual(_pending_installments(other), CAPPED_INSTALLMENT)

    def test_the_installment_lands_inside_the_requested_pay_period(self):
        """Duplicate safety is scoped to a pay period, so the row has to carry a
        payroll_date inside the period that was asked for."""
        advance = self._advance()
        with self._policy():
            installment = schedule_recovery_deduction(advance, self.payroll_date)
        stored = str(frappe.db.get_value("Additional Salary", installment, "payroll_date"))
        self.assertEqual(stored, self.payroll_date)
        # str() on both sides: get_first_day/get_last_day return date objects.
        self.assertGreaterEqual(stored, str(get_first_day(self.payroll_date)))
        self.assertLessEqual(stored, str(get_last_day(self.payroll_date)))

    # Clause: a re-run must not repay the same advance twice.

    def test_a_second_run_in_the_same_pay_period_queues_nothing(self):
        """A scheduler retry or a second manual click is a no-op — one
        installment per advance per pay period, counting drafts."""
        advance = self._advance()
        with self._policy():
            first = schedule_recovery_deduction(advance, self.payroll_date)
            second = schedule_recovery_deduction(advance, self.payroll_date)

        self.assertTrue(first)
        self.assertIsNone(second, "a repeat run in the same pay period must queue nothing")
        self.assertEqual(
            self._installment_count(advance),
            1,
            "exactly one installment may exist for this advance and pay period",
        )

    def test_a_queued_draft_is_subtracted_from_the_outstanding_balance(self):
        """A draft has not moved the native balance yet, so the engine subtracts
        it by hand — otherwise the next period would queue the same money
        twice."""
        advance = self._advance(paid=CAPPED_INSTALLMENT + 250.0)
        with self._policy():
            self.assertEqual(compute_recovery_installment(advance, self.payroll_date), CAPPED_INSTALLMENT)
            self.assertTrue(schedule_recovery_deduction(advance, self.payroll_date))
            next_period = compute_recovery_installment(advance, add_months(self.payroll_date, 1))

        self.assertEqual(_pending_installments(advance), CAPPED_INSTALLMENT)
        self.assertEqual(
            next_period,
            250.0,
            "the queued draft must already be off the outstanding balance",
        )

    def test_a_fully_committed_pay_period_defers_the_recovery(self):
        """Availability is the wage left after the deductions already claiming
        that period. A wage fully spoken for defers rather than pushing net pay
        negative."""
        advance = self._advance()
        frappe.get_doc(
            {
                "doctype": "Additional Salary",
                "employee": self.employee,
                "company": self.company,
                "currency": self.currency,
                "salary_component": self.deduction_component,
                "amount": WAGE,
                "payroll_date": self.payroll_date,
                "overwrite_salary_structure_amount": 0,
            }
        ).insert(ignore_permissions=True)

        with self._policy():
            self.assertEqual(
                compute_recovery_installment(advance, self.payroll_date),
                0.0,
                "a pay period already committed in full must defer, not deduct",
            )
            self.assertIsNone(
                schedule_recovery_deduction(advance, self.payroll_date),
                "a deferred period must queue no installment at all",
            )
        self.assertEqual(self._installment_count(advance), 0)

    # Clause: submit moves the recovered balance and cancel returns it.

    def test_submitting_the_installment_updates_the_recovered_balance(self):
        """Natively: HRMS's own ``on_submit`` moves ``return_amount`` on the
        advance. apex never recomputes it — it only supplies the
        ref_doctype/ref_docname pair HRMS keys on."""
        advance = self._advance()
        with self._policy():
            installment = schedule_recovery_deduction(advance, self.payroll_date)

        self.assertEqual(self._return_amount(advance), 0.0)
        frappe.get_doc("Additional Salary", installment).submit()

        self.assertEqual(
            self._return_amount(advance),
            CAPPED_INSTALLMENT,
            "submitting the installment must move the advance's recovered balance",
        )

    def test_the_recovered_balance_reduces_what_is_still_recoverable(self):
        """The balance the submit moved is real: outstanding is measured as
        paid - returned, so the next period sees less left to recover."""
        advance = self._advance(paid=CAPPED_INSTALLMENT + 100.0)
        with self._policy():
            installment = schedule_recovery_deduction(advance, self.payroll_date)
            frappe.get_doc("Additional Salary", installment).submit()
            remaining = compute_recovery_installment(advance, add_months(self.payroll_date, 1))

        self.assertEqual(
            remaining,
            100.0,
            "only the un-recovered remainder of what the company paid may still be taken",
        )

    def test_cancelling_the_installment_reverses_the_recovered_balance(self):
        """The mirror of the submit: HRMS's own ``on_cancel`` subtracts the same
        amount back off ``return_amount``, so a reversed installment leaves the
        advance exactly as it was."""
        advance = self._advance()
        with self._policy():
            installment = schedule_recovery_deduction(advance, self.payroll_date)

        doc = frappe.get_doc("Additional Salary", installment)
        doc.submit()
        self.assertEqual(self._return_amount(advance), CAPPED_INSTALLMENT)

        doc.reload()
        doc.cancel()
        self.assertEqual(
            self._return_amount(advance),
            0.0,
            "cancelling the installment must reverse the recovered balance",
        )

    # Clause: the component must be of type Deduction, or payroll PAYS the damage.
    # Its ledger account is site payroll config apex never writes — see the
    # rationale on _recovery_component for why no account comparison happens here.

    def test_an_earning_component_is_refused(self):
        """An Earning component would silently PAY the worker the damage, so the
        engine must refuse rather than post it."""
        self.assertIsNone(_recovery_component(_StubPolicy(salary_component=self.earning_component)))

        advance = self._advance()
        with self._policy(salary_component=self.earning_component):
            self.assertIsNone(
                schedule_recovery_deduction(advance, self.payroll_date),
                "no installment may be scheduled through an Earning component",
            )
        self.assertEqual(self._installment_count(advance), 0)

    def test_a_deduction_component_is_accepted(self):
        """Non-vacuity for the guard above: the same code path accepts a
        correctly typed component."""
        self.assertEqual(
            _recovery_component(_StubPolicy(salary_component=self.deduction_component)),
            self.deduction_component,
        )

    def test_a_policy_without_a_component_schedules_nothing(self):
        advance = self._advance()
        self.assertIsNone(_recovery_component(_StubPolicy(salary_component=None)))
        with self._policy(salary_component=None):
            self.assertIsNone(schedule_recovery_deduction(advance, self.payroll_date))
        self.assertEqual(self._installment_count(advance), 0)

    def test_a_disabled_damage_rule_schedules_nothing(self):
        """The shipped default: with the Damage rule off, no wage is touched."""
        advance = self._advance()
        with self._policy(rule=False):
            self.assertEqual(compute_recovery_installment(advance, self.payroll_date), 0.0)
            self.assertIsNone(schedule_recovery_deduction(advance, self.payroll_date))
        self.assertEqual(self._installment_count(advance), 0)

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
                purpose=f"A-102 wrong account {_tag()}",
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
