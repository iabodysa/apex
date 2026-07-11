# Copyright (c) 2026, AFMCO and contributors
"""Tests for the payroll-gate helpers (P-192).

``valid_sa_iban`` is bench-free (a pure format rule), unit-tested directly. The
maker-checker consent gate (``additional_salary_validate``) needs a Frappe bench
and is proven below with SYNTHETIC frappe._dict docs (no master cascade, no real
IBAN / cap / worker value):

* UNCONSENTED-BLOCKED  — a P-192 payroll-category Deduction with no verified
  Deduction Consent cannot post.
* CATEGORY-8 HELD      — an iqama-renewal-recharge (component #8) deduction is
  held until the D9 legal-clearance flag on Salary Deduction Policy is set.
* PASSTHROUGH          — a non-Deduction, or a Deduction with no pay_category, is
  left untouched (other structure components are not gated).

GAPS (reported, NOT worked around): the spec guards "slips only after the
declaration is received", "component #7 -> Loan Repayment mapping", and "WPS SIF
totals tie to the slips" have NO committed function in ``payroll_gate.py`` /
``payroll_run.py`` to assert against — they are payroll-run aggregation behaviour
not yet expressed as a testable public surface. Left as an integrator step.
"""

from __future__ import annotations

import unittest

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.logistay.payroll_gate import IQAMA_RECHARGE_CATEGORY, additional_salary_validate, valid_sa_iban


class TestValidSaIban(unittest.TestCase):
    def test_none_and_empty_fail_closed(self):
        self.assertFalse(valid_sa_iban(None))
        self.assertFalse(valid_sa_iban(""))
        self.assertFalse(valid_sa_iban("   "))

    def test_wrong_country_or_length_fail(self):
        self.assertFalse(valid_sa_iban("AE" + "0" * 22))  # wrong country
        self.assertFalse(valid_sa_iban("SA" + "0" * 21))  # too short
        self.assertFalse(valid_sa_iban("SA" + "0" * 23))  # too long
        self.assertFalse(valid_sa_iban("SA" + "0" * 21 + "X"))  # non-digit body

    def test_well_formed_structure_passes(self):
        # 'SA' + 22 digits; a structural placeholder, not a real account.
        self.assertTrue(valid_sa_iban("SA" + "1" * 22))
        self.assertTrue(valid_sa_iban("sa " + "2" * 22))  # normalized (case/space)


class TestConsentGate(FrappeTestCase):
    """additional_salary_validate — the hard maker-checker consent gate."""

    def test_non_deduction_is_untouched(self):
        doc = frappe._dict(type="Earning", pay_category="Any", amount=100)
        self.assertIsNone(additional_salary_validate(doc))  # no throw

    def test_deduction_without_pay_category_is_untouched(self):
        # A plain structure Deduction (no P-192 category) is not gated.
        doc = frappe._dict(type="Deduction", amount=100)
        self.assertIsNone(additional_salary_validate(doc))  # no throw

    def test_payroll_category_deduction_without_consent_is_blocked(self):
        doc = frappe._dict(
            type="Deduction",
            pay_category="Advance Recovery",  # synthetic non-held category
            pay_consent=None,
            amount=100,
            payroll_date="2026-03-31",
        )
        with self.assertRaises(frappe.ValidationError):
            additional_salary_validate(doc)

    def test_category_8_iqama_recharge_is_held(self):
        # Component #8 stays closed until the D9 legal-clearance flag is set.
        # On a fresh bench the flag is unset -> the deduction is held.
        if frappe.db.get_single_value("Salary Deduction Policy", "pay_category_8_legal_cleared"):
            self.skipTest("category-8 legal clearance already granted on this bench")
        doc = frappe._dict(
            type="Deduction",
            pay_category=IQAMA_RECHARGE_CATEGORY,
            pay_consent=None,
            amount=100,
            payroll_date="2026-03-31",
        )
        with self.assertRaises(frappe.ValidationError):
            additional_salary_validate(doc)


if __name__ == "__main__":
    unittest.main()
