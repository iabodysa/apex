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

A-019 additions (pure decision cores, bench-free):

* DECLARATION-GATE     — a run at/after Slips Built with no RECEIVED declaration is
  blocked; the same run WITH one passes, and pre-slip states pass regardless.
* COMPONENT-ROUTING    — deduction component #7 routes to the Loan Repayment salary
  component from the routing DATA; #8 (iqama-renewal-recharge) is held (routes None).
"""

from __future__ import annotations

import unittest

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.logistay import payroll_gate
from apex.logistay.payroll_gate import (
    IQAMA_RECHARGE_CATEGORY,
    additional_salary_validate,
    enforce_declaration_gate,
    requires_declaration,
    route_deduction_component,
    valid_sa_iban,
)


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


class TestDeclarationGate(FrappeTestCase):
    """enforce_declaration_gate — slips are held until the declaration is received."""

    def test_pre_slip_states_pass_without_declaration(self):
        # Draft / Declaration Requested / Declaration Received do not build slips yet.
        for status in ("Draft", "Declaration Requested", "Declaration Received"):
            self.assertFalse(requires_declaration(status))
            # No throw even with declaration_received=False.
            self.assertIsNone(enforce_declaration_gate(status, False))

    def test_slip_build_state_without_declaration_is_blocked(self):
        self.assertTrue(requires_declaration("Slips Built"))
        with self.assertRaises(frappe.ValidationError):
            enforce_declaration_gate("Slips Built", declaration_received=False)

    def test_slip_build_state_with_received_declaration_is_allowed(self):
        # Same state, declaration RECEIVED -> passes. Proves the gate keys off the
        # boolean, not merely off the status (non-tautology).
        self.assertIsNone(enforce_declaration_gate("Slips Built", declaration_received=True))


class TestComponentRouting(FrappeTestCase):
    """route_deduction_component — the numbered D-taxonomy -> Salary Component map."""

    # Synthetic routing DATA (never a real AFMCO config): component #7 -> Loan Repayment.
    ROUTING = {7: "Loan Repayment", 3: "Operational Deduction"}
    HELD = {8}  # #8 iqama-renewal-recharge is held out of payroll.

    def test_component_7_routes_to_loan_repayment(self):
        self.assertEqual(
            route_deduction_component(7, self.ROUTING, self.HELD), "Loan Repayment"
        )

    def test_component_8_is_held(self):
        # Held component routes NOWHERE.
        self.assertIsNone(route_deduction_component(8, self.ROUTING, self.HELD))

    def test_wrong_routing_data_would_not_return_loan_repayment(self):
        # Non-tautology: feed a map that routes #7 elsewhere -> the #7==Loan assertion
        # would fail. Here we prove the function faithfully returns the DATA it is given.
        self.assertEqual(
            route_deduction_component(7, {7: "Operational Deduction"}, self.HELD),
            "Operational Deduction",
        )

    def test_unmapped_non_held_component_fails_closed(self):
        with self.assertRaises(frappe.ValidationError):
            route_deduction_component(5, self.ROUTING, self.HELD)


class TestComponentRoutingWiring(FrappeTestCase):
    """Proves route_deduction_component is WIRED into the real deduction call site.

    ``additional_salary_validate`` (the ``Additional Salary.validate`` doc-event) is
    where a P-192 deduction's target ``salary_component`` is resolved before HRMS
    pulls it onto a Salary Slip. These tests inject SYNTHETIC routing DATA (never a
    real AFMCO config) at the loader seam and drive the real entry function - the same
    code that fires in production - so a #7 deduction lands on Loan Repayment and a
    held category is left un-routed. Without the wired ``_apply_component_routing``
    call, ``salary_component`` would never change (non-tautology).
    """

    def setUp(self):
        self._orig_load = payroll_gate._load_deduction_routing
        self._orig_consent = payroll_gate._require_verified_consent
        # Consent verification needs seeded masters; stub it so this test isolates
        # the routing wiring only (consent itself is covered by TestConsentGate).
        payroll_gate._require_verified_consent = lambda doc: None

    def tearDown(self):
        payroll_gate._load_deduction_routing = self._orig_load
        payroll_gate._require_verified_consent = self._orig_consent

    def _stub_routing(self, routing_map, held):
        payroll_gate._load_deduction_routing = lambda: (routing_map, held)

    def test_wired_validate_routes_component_7_to_loan_repayment(self):
        # Component #7 = "Loan Balance Offset"; the seeded DATA routes it to the stock
        # Loan Repayment component. Driving the REAL validate rewrites salary_component.
        self._stub_routing({"Loan Balance Offset": "Loan Repayment"}, {IQAMA_RECHARGE_CATEGORY})
        doc = frappe._dict(
            type="Deduction",
            pay_category="Loan Balance Offset",
            salary_component="Some Wrong Component",
            amount=100,
            payroll_date="2026-03-31",
        )
        additional_salary_validate(doc)
        self.assertEqual(doc.salary_component, "Loan Repayment")

    def test_wired_validate_leaves_held_category_unrouted(self):
        # A held (disabled) category routes NOWHERE: its component is untouched and no
        # rewrite happens. (Use a non-iqama held category so _block_held_category is
        # a pass-through and we observe the routing decision, not the hard block.)
        self._stub_routing({}, {"Vehicle Damages"})
        doc = frappe._dict(
            type="Deduction",
            pay_category="Vehicle Damages",
            salary_component="Native Component",
            amount=100,
            payroll_date="2026-03-31",
        )
        additional_salary_validate(doc)
        self.assertEqual(doc.salary_component, "Native Component")

    def test_wired_validate_leaves_ungoverned_category_untouched(self):
        # A category the policy does not govern (not mapped, not held) keeps the chosen
        # component - routing only fires on real DATA, so no regression for other
        # deductions. Proves the rewrite is data-driven, not unconditional.
        self._stub_routing({"Loan Balance Offset": "Loan Repayment"}, set())
        doc = frappe._dict(
            type="Deduction",
            pay_category="Traffic Fine",
            salary_component="Native Component",
            amount=100,
            payroll_date="2026-03-31",
        )
        additional_salary_validate(doc)
        self.assertEqual(doc.salary_component, "Native Component")


if __name__ == "__main__":
    unittest.main()
