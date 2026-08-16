# Copyright (c) 2026, AFMCO and contributors
"""Tests for the Vehicle Utilisation report execute().

Asserts the column contract and that execute() runs end-to-end (defensive about
the Vehicle Utilisation Snapshot source DocType) returning a data list whose
per-vehicle rows carry every declared field. Requires a live site.

The row test seeds two snapshots for one vehicle: on an empty test database the
per-row loop had nothing to iterate, so the row-shape assertion never executed
and the per-vehicle sum/average roll-up went unproven. The vehicle those snapshots
hang off is the shipped fixture; only the snapshots — the report's subject — are built.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.tests import factories
from frappe.utils import add_days, today

from apex.salis.report.vehicle_utilisation.vehicle_utilisation import execute

test_dependencies = ["Salis Vehicle"]

PLATE = "_T ABC 1001"

_EXPECTED_FIELDS = [
    "vehicle",
    "snapshots",
    "trips_count",
    "idle_days",
    "period_days",
    "utilisation_pct",
]


class TestVehicleUtilisation(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        """The two snapshots are built ONCE for the class, not once per case.

        A DB-level unique constraint covers (vehicle, snapshot_date), and the borrowed
        vehicle is the same row for every case, so a per-case insert of today's snapshot
        collides with the one the previous case left behind. Nothing here writes to them,
        so one build serves the whole class and the class rollback takes them away again.
        """
        super().setUpClass()
        # A vehicle of this class's own, never the shipped `_T ABC 1001`. That plate is
        # VEH-000001, which the shipped `vehicle_utilisation_snapshot` fixture already carries
        # a snapshot for — so `snapshots` read 3 where the class had built 2, and the test
        # graded the site's fixtures rather than the rollup.
        cls.vehicle = factories.make_vehicle(f"_T UTIL {frappe.generate_hash(length=12)}")
        cls._snapshot(today(), trips=10, idle=2, util=80.0)
        cls._snapshot(add_days(today(), -7), trips=6, idle=4, util=60.0)

    @classmethod
    def _snapshot(cls, snapshot_date, trips, idle, util):
        return frappe.get_doc(
            {
                "doctype": "Vehicle Utilisation Snapshot",
                "vehicle": cls.vehicle,
                "snapshot_date": snapshot_date,
                "period_days": 7,
                "trips_count": trips,
                "idle_days": idle,
                "utilisation_pct": util,
            }
        ).insert(ignore_permissions=True).name

    def setUp(self):
        frappe.set_user("Administrator")

    def test_columns_contract(self):
        columns, data, *_rest = execute({})
        self.assertEqual([c["fieldname"] for c in columns], _EXPECTED_FIELDS)
        self.assertIsInstance(data, list)

    def test_rows_carry_expected_keys(self):
        _columns, data, *_rest = execute({})
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
        _columns, data, *_rest = execute({"vehicle": self.vehicle})
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
