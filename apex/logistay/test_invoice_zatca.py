# Copyright (c) 2026, AFMCO and contributors
"""P-191 acceptance tests — Invoice assembly present-set + fail-closed issue gate.

The invoice module is deliberately thin (native-first): stock ERPNext Sales
Invoice computes every amount/tax/total and owns the gapless naming series; the
procured KSA/ZATCA app stamps the e-invoice. The committed logistay code owns
only three things, all proven here against SYNTHETIC fixtures:

* present_set_targets (D8) — which of the up-to-4 documents a client receives:
  only components BOTH enabled AND fired this period; riders collapse onto the
  main timesheet. A component that did NOT fire yields NO target — i.e. a sample
  / dry round produces nothing, so it consumes NO invoice (ZATCA) number.
* naming_matches       — the pre-issue naming gate: exact or trim/case/whitespace
  only, never fuzzy.
* enforce_issuance_gate — FAIL-CLOSED before_submit gate: an eos line with no
  transfer ref, a missing Client Name Registry, or (P-193) an unresolved
  authority BLOCKS issuance.

TestPresentSet + TestNamingMatch are PURE (no frappe runtime) and run standalone:
    python -m unittest apex.logistay.test_invoice_zatca.TestPresentSet
    python -m unittest apex.logistay.test_invoice_zatca.TestNamingMatch

GAPS (reported, NOT worked around):
* "Gapless SINV numbers" and "a reversal issues credit notes against all
  originals" are stock ERPNext behaviours (naming series + Sales Invoice
  is_return credit note). No committed logistay function issues or renumbers
  invoices, so asserting gaplessness / credit-note fan-out here would test
  ERPNext, not this engine. The present-set filter (what MAY be issued) is the
  committed surface and IS asserted; the numbering/credit-note reproduction is
  an integrator step on a bench with ERPNext + the ZATCA app installed.
* "Client approval unblocks stamping" flows through the P-193 governance gate
  (enforce_gate) and is asserted in test_governance.py; here only the FAIL-CLOSED
  block branches that live in logistay code are asserted.
"""

from __future__ import annotations

import unittest

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.logistay.invoice_assembly import (
    enforce_issuance_gate,
    naming_matches,
    present_set_targets,
)


def _suffix() -> str:
    return frappe.generate_hash(length=12)


class TestPresentSet(unittest.TestCase):
    """D8 present-set filter — pure, side-effect free."""

    def test_enabled_and_fired_component_routes_to_own_document(self):
        rules = [
            {"inv_component": "levy", "inv_is_enabled": 1, "inv_target_document": "levy"},
        ]
        self.assertEqual(present_set_targets(rules, ["levy"]), {"levy": ["levy"]})

    def test_unfired_component_yields_no_target_consumes_no_number(self):
        # A dry / sample round: the component did not fire -> nothing is produced,
        # so no invoice (ZATCA) number is ever consumed.
        rules = [
            {"inv_component": "levy", "inv_is_enabled": 1, "inv_target_document": "levy"},
        ]
        self.assertEqual(present_set_targets(rules, []), {})

    def test_disabled_component_is_never_in_the_set(self):
        rules = [
            {"inv_component": "levy", "inv_is_enabled": 0, "inv_target_document": "levy"},
        ]
        self.assertEqual(present_set_targets(rules, ["levy"]), {})

    def test_rider_components_collapse_onto_main_timesheet(self):
        rules = [
            {"inv_component": "gosi_fee", "inv_is_enabled": 1, "inv_target_document": "own"},
            {"inv_component": "charge_fee", "inv_is_enabled": 1, "inv_target_document": "own"},
            {"inv_component": "timesheet", "inv_is_enabled": 1, "inv_target_document": "main_timesheet"},
        ]
        targets = present_set_targets(rules, ["gosi_fee", "charge_fee", "timesheet"])
        self.assertEqual(set(targets), {"main_timesheet"})
        self.assertCountEqual(targets["main_timesheet"], ["gosi_fee", "charge_fee", "timesheet"])

    def test_explicit_rides_on_main_timesheet_collapses(self):
        rules = [
            {
                "inv_component": "overtime",
                "inv_is_enabled": 1,
                "inv_target_document": "overtime",
                "inv_rides_on": "main_timesheet",
            },
        ]
        self.assertEqual(present_set_targets(rules, ["overtime"]), {"main_timesheet": ["overtime"]})


class TestNamingMatch(unittest.TestCase):
    """Naming gate — exact or normalized, never fuzzy."""

    def test_exact_match_passes(self):
        self.assertTrue(naming_matches("Acme LLC", "300000000000003", "Acme LLC", "300000000000003"))

    def test_exact_mismatch_fails(self):
        self.assertFalse(naming_matches("Acme LLC", "300000000000003", "Acme  LLC", "300000000000003"))

    def test_normalized_absorbs_case_and_whitespace(self):
        self.assertTrue(
            naming_matches(
                "Acme LLC", "300000000000003", "  acme   llc ", "300000000000003", "normalized"
            )
        )

    def test_normalized_is_not_fuzzy(self):
        # A single-character difference is still a mismatch even normalized.
        self.assertFalse(
            naming_matches("Acme LLC", "300000000000003", "Acme LLD", "300000000000003", "normalized")
        )


class TestIssuanceGateFailClosed(FrappeTestCase):
    """enforce_issuance_gate blocks on every unresolved condition (fail-closed)."""

    def test_non_assembly_invoice_passes_through(self):
        doc = frappe._dict()  # a plain ERPNext SINV: no inv_assembly_run
        # Must NOT raise; returns None and leaves stock behaviour untouched.
        self.assertIsNone(enforce_issuance_gate(doc))

    def test_eos_line_without_transfer_ref_is_blocked(self):
        doc = frappe._dict(
            inv_assembly_run=f"LGZT-ASM-{_suffix()}",
            inv_component_type="eos",
            inv_eos_transfer_ref=None,
        )
        with self.assertRaises(frappe.ValidationError):
            enforce_issuance_gate(doc)

    def test_missing_client_name_registry_holds_issuance(self):
        # A non-existent assembly run resolves to no client -> no Client Name
        # Registry -> cannot verify the legal name -> FAIL-CLOSED hold.
        doc = frappe._dict(
            inv_assembly_run=f"LGZT-ASM-{_suffix()}",
            customer_name="Synthetic Co",
            tax_id="300000000000003",
            grand_total=1000,
        )
        with self.assertRaises(frappe.ValidationError):
            enforce_issuance_gate(doc)


if __name__ == "__main__":
    unittest.main()
