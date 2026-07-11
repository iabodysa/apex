# Copyright (c) 2026, AFMCO and contributors
"""Tests for the WPS SIF assembly (P-192 / A-019).

``build_wps_sif`` groups Salary Slips per establishment; ``sif_reconciles`` proves the
per-establishment totals equal the exact sum of the underlying slip nets. Pure, bench-
free: exercised with SYNTHETIC round slips (no real AFMCO worker, IBAN, or amount).
"""

from __future__ import annotations

import unittest

from apex.logistay.wps_sif import build_wps_sif, sif_reconciles

# Synthetic slips: two establishments, deterministic round nets. No real values.
SLIPS = [
    {"employee": "W-1", "establishment": "EST-A", "net": 1000},
    {"employee": "W-2", "establishment": "EST-A", "net": 1500},
    {"employee": "W-3", "establishment": "EST-B", "net": 2000},
]


class TestWpsSif(unittest.TestCase):
    def test_per_establishment_totals_tie_to_slip_nets(self):
        sif = build_wps_sif(SLIPS)
        ests = sif["establishments"]
        # EST-A = 1000 + 1500 = 2500 over 2 slips; EST-B = 2000 over 1 slip.
        self.assertEqual(ests["EST-A"]["total_net"], 2500.0)
        self.assertEqual(ests["EST-A"]["record_count"], 2)
        self.assertEqual(ests["EST-B"]["total_net"], 2000.0)
        self.assertEqual(ests["EST-B"]["record_count"], 1)

    def test_grand_total_equals_sum_of_all_nets(self):
        sif = build_wps_sif(SLIPS)
        self.assertEqual(sif["grand_total_net"], sum(s["net"] for s in SLIPS))

    def test_reconcile_passes_for_faithful_sif(self):
        self.assertTrue(sif_reconciles(build_wps_sif(SLIPS), SLIPS))

    def test_tampered_total_fails_reconcile(self):
        # Non-tautology: corrupt one establishment total -> reconcile must fail.
        sif = build_wps_sif(SLIPS)
        sif["establishments"]["EST-A"]["total_net"] += 1
        self.assertFalse(sif_reconciles(sif, SLIPS))

    def test_dropped_slip_fails_reconcile(self):
        # A SIF built from fewer slips than exist must not reconcile to the full set.
        partial = build_wps_sif(SLIPS[:2])
        self.assertFalse(sif_reconciles(partial, SLIPS))

    def test_deterministic_establishment_ordering(self):
        # Shuffled input -> same sorted establishment key order (stable file output).
        a = list(build_wps_sif(SLIPS)["establishments"].keys())
        b = list(build_wps_sif(list(reversed(SLIPS)))["establishments"].keys())
        self.assertEqual(a, b)
        self.assertEqual(a, sorted(a))


if __name__ == "__main__":
    unittest.main()
