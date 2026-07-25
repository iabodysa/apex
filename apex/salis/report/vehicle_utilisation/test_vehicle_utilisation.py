# Copyright (c) 2026, AFMCO and contributors
"""Tests for the Vehicle Utilisation report execute().

Asserts the column contract and that execute() runs end-to-end (defensive about
the Vehicle Utilisation Snapshot source DocType) returning a data list whose
per-vehicle rows carry every declared field. Requires a live site."""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.salis.report.vehicle_utilisation.vehicle_utilisation import execute

_EXPECTED_FIELDS = [
    "vehicle",
    "snapshots",
    "trips_count",
    "idle_days",
    "period_days",
    "utilisation_pct",
]


class TestVehicleUtilisation(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")

    def test_columns_contract(self):
        columns, data = execute({})
        self.assertEqual([c["fieldname"] for c in columns], _EXPECTED_FIELDS)
        self.assertIsInstance(data, list)

    def test_rows_carry_expected_keys(self):
        _columns, data = execute({})
        for row in data:
            for key in _EXPECTED_FIELDS:
                self.assertIn(key, row)
