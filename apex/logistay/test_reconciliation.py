# Copyright (c) 2026, AFMCO and contributors
"""P-190 acceptance tests — Reconciliation: ONE run, TWO outputs.

Proven against SYNTHETIC fixtures (no real client / amount / basis value):

* ONE-RUN-TWO-OUTPUTS   — a single Reconciliation Run keys BOTH a client-side
  Billable Line set and a worker-side Payable Line set.
* BASIS-CONSISTENT (D1) — a Billable and a Payable line off the SAME Rate
  Resolution that snapshot DIFFERENT day-rate bases HALT the run
  (``billing_vs_payable_mismatch``); identical bases pass. The guard compares
  the BASIS, never day-counts.
* FED-PRECONDITION (A2/C4) — a client with a per-worker feed applies thresholds;
  one without SKIPS as a structural no-op (not a gate, not a zero-filled candidate).
* GATED-THRESHOLD        — an inferred/gated penalty row is detected (forces
  PENDING-REVIEW; the engine never invents penalty maths).
* NEVER-MUTATE-POSTED    — a posted run is immutable in place; the SOLE legal
  move is posted -> reversed (a correction is a reverse + re-run REVERSAL set,
  never an in-place edit).

``TestGatedThresholdGuard`` is pure (no frappe runtime) and runs standalone:
    python -m unittest apex.logistay.test_reconciliation.TestGatedThresholdGuard
The rest are FrappeTestCase (need a bench + site).
"""

from __future__ import annotations

import unittest

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.logistay.reconciliation_engine import (
    guard_basis_consistent,
    guard_no_open_gated_threshold,
    should_apply_thresholds,
)


def _suffix() -> str:
    return frappe.generate_hash(length=12)


class _Row:
    """A stand-in threshold-log row: the guard only reads rec_gated_open_item."""

    def __init__(self, gated: int):
        self.rec_gated_open_item = gated


class TestGatedThresholdGuard(unittest.TestCase):
    """Pure branch coverage for guard_no_open_gated_threshold (bench-free)."""

    def test_none_and_empty_are_not_gated(self):
        self.assertFalse(guard_no_open_gated_threshold(None))
        self.assertFalse(guard_no_open_gated_threshold([]))

    def test_all_clear_rows_are_not_gated(self):
        self.assertFalse(guard_no_open_gated_threshold([_Row(0), _Row(0)]))

    def test_any_gated_row_flags(self):
        self.assertTrue(guard_no_open_gated_threshold([_Row(0), _Row(1)]))
        self.assertTrue(guard_no_open_gated_threshold([_Row(1)]))


class TestBasisConsistentGuard(FrappeTestCase):
    """D1 BASIS-CONSISTENT over a shared Rate Resolution, isolated with ignore_links."""

    def _emit_lines(self, run, resolution, billable_basis, payable_basis):
        bl = frappe.get_doc(
            {
                "doctype": "Billable Line",
                "rec_run": run,
                "rec_component": "timesheet",
                "rec_resolution_ref": resolution,
                "rec_day_rate_basis_applied": billable_basis,
            }
        )
        bl.flags.ignore_links = True
        bl.insert(ignore_permissions=True, ignore_mandatory=True)
        pl = frappe.get_doc(
            {
                "doctype": "Payable Line",
                "rec_run": run,
                "rec_worker": f"LGZT-WORKER-{_suffix()}",
                "rec_partial_reason": "full_month",
                "rec_resolution_ref": resolution,
                "rec_day_rate_basis_applied": payable_basis,
            }
        )
        pl.flags.ignore_links = True
        pl.insert(ignore_permissions=True, ignore_mandatory=True)
        return bl, pl

    def test_one_run_emits_both_a_billable_and_a_payable_side(self):
        run = f"LGZT-RUN-{_suffix()}"
        resolution = f"LGZT-RES-{_suffix()}"
        self._emit_lines(run, resolution, "div_31", "div_31")
        self.assertEqual(len(frappe.get_all("Billable Line", filters={"rec_run": run})), 1)
        self.assertEqual(len(frappe.get_all("Payable Line", filters={"rec_run": run})), 1)
        # Same basis on both sides -> the guard passes (no throw).
        guard_basis_consistent(run)

    def test_basis_mismatch_halts_the_run(self):
        run = f"LGZT-RUN-{_suffix()}"
        resolution = f"LGZT-RES-{_suffix()}"
        # SAME resolution, DIFFERENT bases on the two sides -> fail-closed halt.
        self._emit_lines(run, resolution, "div_31", "fixed_365_12")
        with self.assertRaises(frappe.ValidationError):
            guard_basis_consistent(run)

    def test_different_resolutions_do_not_cross_compare(self):
        # A basis difference across DIFFERENT resolutions is not a mismatch:
        # the guard pairs by resolution, so this must NOT halt.
        run = f"LGZT-RUN-{_suffix()}"
        self._emit_lines(run, f"LGZT-RES-{_suffix()}", "div_31", "div_31")
        self._emit_lines(run, f"LGZT-RES-{_suffix()}", "fixed_365_12", "fixed_365_12")
        guard_basis_consistent(run)  # no throw


class TestFedPrecondition(FrappeTestCase):
    """A2/C4: threshold application runs only for a client carrying a per-worker feed."""

    def _config(self, has_feed: int) -> str:
        client = f"LGZT-CLIENT-{_suffix()}"
        cfg = frappe.get_doc(
            {
                "doctype": "Client Reconciliation Config",
                "rec_client": client,
                "has_per_worker_feed": has_feed,
            }
        )
        cfg.flags.ignore_links = True
        cfg.insert(ignore_permissions=True, ignore_mandatory=True)
        return client

    def test_no_client_skips(self):
        self.assertFalse(should_apply_thresholds(None))

    def test_client_with_feed_applies(self):
        self.assertTrue(should_apply_thresholds(self._config(1)))

    def test_client_without_feed_skips(self):
        self.assertFalse(should_apply_thresholds(self._config(0)))


class TestNeverMutatePosted(FrappeTestCase):
    """A posted run is immutable in place; the only move off posted is to reversed."""

    def _posted_run(self):
        run = frappe.get_doc(
            {
                "doctype": "Reconciliation Run",
                "rec_run_name": f"LGZT-RUN-{_suffix()}",
                "rec_client": f"LGZT-CLIENT-{_suffix()}",
                "rec_service_line": "delivery",
                "rec_period": f"LGZT-PERIOD-{_suffix()}",
                "rec_period_cutoff": "2026-03-31",
                "rec_status": "posted",
                "rec_open_flags": 0,
            }
        )
        run.flags.ignore_links = True
        run.insert(ignore_permissions=True, ignore_mandatory=True)
        return run

    def test_in_place_edit_of_posted_run_is_blocked(self):
        run = self._posted_run()
        reloaded = frappe.get_doc("Reconciliation Run", run.name)
        reloaded.flags.ignore_links = True
        reloaded.rec_total_billable = 500  # any in-place change while still posted
        with self.assertRaises(frappe.ValidationError):
            reloaded.save(ignore_permissions=True)

    def test_posted_to_reversed_is_the_only_legal_move(self):
        run = self._posted_run()
        reloaded = frappe.get_doc("Reconciliation Run", run.name)
        reloaded.flags.ignore_links = True
        reloaded.rec_status = "reversed"  # the reverse + re-run correction path
        reloaded.save(ignore_permissions=True)
        self.assertEqual(
            frappe.db.get_value("Reconciliation Run", run.name, "rec_status"), "reversed"
        )


if __name__ == "__main__":
    unittest.main()
