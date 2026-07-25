# Copyright (c) 2026, AFMCO and contributors
"""Tests for the Vehicle Utilisation report execute().

Asserts the column contract and that execute() runs end-to-end (defensive about
the Vehicle Utilisation Snapshot source DocType) returning a data list whose
per-vehicle rows carry every declared field. Requires a live site.

The row test seeds two snapshots for one vehicle: on an empty test database the
per-row loop had nothing to iterate, so the row-shape assertion never executed
and the per-vehicle sum/average roll-up went unproven."""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today

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
        tag = frappe.generate_hash(length=12).upper()

        self.vehicle = frappe.get_doc(
            {
                "doctype": "Salis Vehicle",
                "plate_number": f"VUT-{tag}",
                "status": "Active",
            }
        ).insert(ignore_permissions=True).name

        # Two snapshots on distinct dates (a DB-level unique constraint covers
        # (vehicle, snapshot_date)) so the roll-up has something to sum and average.
        self._snapshot(today(), trips=10, idle=2, util=80.0)
        self._snapshot(add_days(today(), -7), trips=6, idle=4, util=60.0)

    def _snapshot(self, snapshot_date, trips, idle, util):
        return frappe.get_doc(
            {
                "doctype": "Vehicle Utilisation Snapshot",
                "vehicle": self.vehicle,
                "snapshot_date": snapshot_date,
                "period_days": 7,
                "trips_count": trips,
                "idle_days": idle,
                "utilisation_pct": util,
            }
        ).insert(ignore_permissions=True).name

    def test_columns_contract(self):
        columns, data = execute({})
        self.assertEqual([c["fieldname"] for c in columns], _EXPECTED_FIELDS)
        self.assertIsInstance(data, list)

    def test_rows_carry_expected_keys(self):
        _columns, data = execute({})
        self.assertTrue(data, "The seeded snapshots must reach the report.")

        checked = 0
        for row in data:
            for key in _EXPECTED_FIELDS:
                self.assertIn(key, row)
            checked += 1
        self.assertEqual(
            checked, len(data), "The per-row assertions must run for every row."
        )

    def test_snapshots_roll_up_into_one_row_per_vehicle(self):
        _columns, data = execute({"vehicle": self.vehicle})
        seeded = [row for row in data if row["vehicle"] == self.vehicle]
        self.assertEqual(
            len(seeded),
            1,
            "Both snapshots belong to one vehicle, so the report must emit a single "
            "rolled-up row.",
        )
        row = seeded[0]
        self.assertEqual(row["snapshots"], 2)
        self.assertEqual(row["trips_count"], 16, "Trips must be summed across snapshots.")
        self.assertEqual(row["idle_days"], 6, "Idle days must be summed across snapshots.")
        self.assertEqual(row["period_days"], 14)
        self.assertEqual(
            row["utilisation_pct"], 70.0, "Utilisation must be averaged, not summed."
        )
