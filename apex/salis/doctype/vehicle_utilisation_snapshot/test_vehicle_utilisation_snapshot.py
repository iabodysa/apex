# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today

from apex.tests.factories import make_vehicle

_TABLE = "tabVehicle Utilisation Snapshot"
_KEY_COLUMNS = ["vehicle", "snapshot_date"]


def _unique_index_columns(table, index_name):
    rows = frappe.db.sql(
        """
        SELECT COLUMN_NAME AS col
        FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = %s
          AND INDEX_NAME = %s
          AND NON_UNIQUE = 0
        ORDER BY SEQ_IN_INDEX
        """,
        (table, index_name),
        as_dict=True,
    )
    return [row["col"] for row in rows]


def _vehicle_utilisation_snapshot(**overrides):
    fields = {
        "doctype": "Vehicle Utilisation Snapshot",
        "vehicle": make_vehicle("_T-VUS 0001"),
        "snapshot_date": today(),
        "period_days": 30,
        "trips_count": 12,
        "idle_days": 6,
        "utilisation_pct": 80.0,
    }
    fields.update(overrides)
    return frappe.get_doc(fields)


class TestVehicleUtilisationSnapshotUniqueIndex(FrappeTestCase):
    def test_the_vehicle_and_snapshot_date_pair_carries_a_unique_index_in_the_database(self):
        self.assertEqual(
            _unique_index_columns(_TABLE, "unique_vus_vehicle_date"), _KEY_COLUMNS
        )


class TestVehicleUtilisationSnapshotOnePerVehiclePerDay(FrappeTestCase):
    def test_a_second_snapshot_of_the_same_vehicle_and_day_is_refused_by_the_database(self):
        day = add_days(today(), 30)
        first = _vehicle_utilisation_snapshot(snapshot_date=day).insert(
            ignore_permissions=True
        )
        second = _vehicle_utilisation_snapshot(
            vehicle=first.vehicle, snapshot_date=day, utilisation_pct=10.0
        )
        with self.assertRaisesRegex(
            frappe.UniqueValidationError, "unique_vus_vehicle_date"
        ):
            second.insert(ignore_permissions=True)

    def test_the_snapshot_of_the_next_day_is_accepted(self):
        day = add_days(today(), 60)
        first = _vehicle_utilisation_snapshot(snapshot_date=day).insert(
            ignore_permissions=True
        )
        second = _vehicle_utilisation_snapshot(
            snapshot_date=add_days(first.snapshot_date, 1)
        ).insert(ignore_permissions=True)
        self.assertTrue(frappe.db.exists("Vehicle Utilisation Snapshot", second.name))

    def test_a_snapshot_of_another_vehicle_on_the_same_day_is_accepted(self):
        day = add_days(today(), 90)
        first = _vehicle_utilisation_snapshot(snapshot_date=day).insert(
            ignore_permissions=True
        )
        second = _vehicle_utilisation_snapshot(
            vehicle=make_vehicle("_T-VUS 0002"), snapshot_date=first.snapshot_date
        ).insert(ignore_permissions=True)
        self.assertTrue(frappe.db.exists("Vehicle Utilisation Snapshot", second.name))


class TestVehicleUtilisationSnapshotCapturedValues(FrappeTestCase):
    def test_a_stored_snapshot_keeps_the_values_it_captured(self):
        doc = _vehicle_utilisation_snapshot(
            trips_count=12, idle_days=6, utilisation_pct=80.0
        ).insert(ignore_permissions=True)
        stored = frappe.db.get_value(
            "Vehicle Utilisation Snapshot",
            doc.name,
            ["trips_count", "idle_days", "utilisation_pct"],
            as_dict=True,
        )
        self.assertEqual(stored.trips_count, 12)
        self.assertEqual(stored.idle_days, 6)
        self.assertEqual(stored.utilisation_pct, 80.0)

    def test_a_snapshot_with_no_vehicle_is_refused_by_the_framework(self):
        doc = _vehicle_utilisation_snapshot(vehicle=None)
        with self.assertRaises(frappe.MandatoryError):
            doc.insert(ignore_permissions=True)
