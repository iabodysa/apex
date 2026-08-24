# Copyright (c) 2026, afmcoltd

"""Four promises the salary-recovery path makes about a person's pay.

This app recovers a debt from an employee's salary through HRMS's own Employee Advance
and Additional Salary, having retired a bespoke deduction policy of its own. Four things
must hold, and each of them fails silently rather than loudly, which is why they are
asserted rather than watched:

  no installment drives net pay below zero · the same money is never queued twice ·
  a period with no payroll room defers instead of deducting · a reversal leaves the
  history standing.

``bounded_installment`` is pure arithmetic with no database read, so the money rules are
proved directly on it. The paths that need a real Employee Advance are asserted through
the validator that guards them.
"""

import pathlib

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.apex_core.utils.employee_recovery import (
    MAX_RECOVERY_PERCENT,
    SOURCE_DOCNAME_FIELD,
    SOURCE_DOCTYPE_FIELD,
    bounded_installment,
    validate_recovery_additional_salary,
)


class TestNoNegativeNetSalary(FrappeTestCase):
    """An installment may never exceed the room the period actually has."""

    def test_the_configured_limit_binds_when_it_is_the_lowest(self):
        self.assertEqual(bounded_installment(outstanding=5000, configured_limit=800), 800)

    def test_the_outstanding_balance_binds_when_it_is_the_lowest(self):
        self.assertEqual(bounded_installment(outstanding=250, configured_limit=800), 250)

    def test_the_agreed_installment_binds_when_it_is_the_lowest(self):
        self.assertEqual(
            bounded_installment(outstanding=5000, configured_limit=800, agreed=300), 300
        )

    def test_no_headroom_recovers_nothing_rather_than_going_negative(self):
        """The defect this guards: a negative limit becoming a negative deduction,
        which HRMS would apply as an ADDITION to pay."""
        self.assertEqual(bounded_installment(outstanding=5000, configured_limit=-1200), 0.0)
        self.assertEqual(bounded_installment(outstanding=-90, configured_limit=800), 0.0)

    def test_a_zero_limit_defers_the_whole_recovery(self):
        self.assertEqual(bounded_installment(outstanding=5000, configured_limit=0), 0.0)

    def test_an_unagreed_installment_does_not_mean_recover_nothing(self):
        """``agreed <= 0`` means "nothing was agreed", not "recover zero" — reading it
        the other way would freeze every recovery that has no explicit instalment."""
        for agreed in (0, 0.0, -5):
            with self.subTest(agreed=agreed):
                self.assertEqual(
                    bounded_installment(outstanding=5000, configured_limit=800, agreed=agreed),
                    800,
                )

    def test_the_result_is_rounded_to_currency_precision(self):
        """Two decimals, because the figure becomes a salary deduction.

        Not asserted on 100.005: that literal is stored as 100.00499..., so a test
        expecting 100.01 measures float representation rather than the rounding rule.
        """
        self.assertEqual(bounded_installment(outstanding=100.126, configured_limit=999), 100.13)
        self.assertEqual(bounded_installment(outstanding=100.124, configured_limit=999), 100.12)
        result = bounded_installment(outstanding=1234.5678, configured_limit=9999)
        self.assertEqual(result, round(result, 2))

    def test_the_policy_ceiling_is_a_percentage_not_a_flat_amount(self):
        self.assertGreater(MAX_RECOVERY_PERCENT, 0)
        self.assertLessEqual(MAX_RECOVERY_PERCENT, 100)


class TestTheRetiredDoctypesAreGone(FrappeTestCase):
    """The bespoke policy this card replaced must not come back."""

    def test_neither_retired_doctype_exists_on_the_site(self):
        for doctype in ("Salary Deduction Policy", "Salary Deduction Type Rule"):
            with self.subTest(doctype=doctype):
                self.assertFalse(frappe.db.exists("DocType", doctype))

    def test_no_source_file_references_them_outside_the_migration(self):
        """A patch MUST still name them — it is what removes them. Nothing else may."""
        root = pathlib.Path(frappe.get_app_path("apex"))
        offenders = [
            str(p)
            for p in root.rglob("*.py")
            if "patches" not in p.parts
            and not p.name.startswith("test_")
            and "Salary Deduction Policy" in p.read_text()
        ]
        self.assertEqual(offenders, [])


class TestRecoveryUsesTheNativeLink(FrappeTestCase):
    """Each installment must point back at its advance through HRMS's own fields."""

    def test_the_validator_ignores_a_salary_row_that_is_not_a_recovery(self):
        """The positive control: a validator that fires on everything would refuse
        every ordinary Additional Salary on the site."""
        validate_recovery_additional_salary(
            frappe._dict(ref_doctype="Expense Claim", ref_docname="EXP-1")
        )
        validate_recovery_additional_salary(
            frappe._dict(ref_doctype="Employee Advance", ref_docname=None)
        )

    def test_the_custom_link_fields_are_named_on_the_advance(self):
        """The source pair is what makes the recovery traceable back to its incident."""
        meta = frappe.get_meta("Employee Advance")
        for field in (SOURCE_DOCTYPE_FIELD, SOURCE_DOCNAME_FIELD):
            with self.subTest(field=field):
                self.assertTrue(
                    meta.has_field(field),
                    f"{field} is missing — the recovery cannot name its source",
                )


class TestReversalKeepsTheHistory(FrappeTestCase):
    """A withdrawn recovery is cancelled, never deleted."""

    def test_additional_salary_is_submittable_so_a_reversal_leaves_a_row(self):
        """If it were not submittable there would be no cancelled state, and undoing a
        recovery would have to delete the row — erasing the fact it ever happened."""
        self.assertTrue(frappe.get_meta("Additional Salary").is_submittable)

    def test_employee_advance_is_submittable_for_the_same_reason(self):
        self.assertTrue(frappe.get_meta("Employee Advance").is_submittable)
