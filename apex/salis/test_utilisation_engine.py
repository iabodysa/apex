# Copyright (c) 2026, AFMCO and contributors
"""Tests for the weekly Vehicle Utilisation Snapshot engine.

Asserts the docstring's contract: over the trailing 7-day window, count
Completed Dispatch Trips per Active vehicle, derive idle days and utilisation
percentage from the distinct days that had at least one trip, and write one
row per vehicle idempotently on vehicle + snapshot_date.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today

from apex.salis.utilisation_engine import weekly_vehicle_utilisation_snapshot


def _vehicle():
    return frappe.get_doc(
        {
            "doctype": "Salis Vehicle",
            "plate_number": f"UTIL-{frappe.generate_hash(length=12)}",
            "status": "Active",
        }
    ).insert(ignore_permissions=True).name


def _completed_trip(vehicle, trip_date):
    """A submitted, Completed Dispatch Trip for ``vehicle`` on ``trip_date``.

    Inserts as a real, valid Planned trip (the controller's ``_guard_initial_status``
    requires a new trip to start Planned, and the doctype carries a mandatory native
    workflow that only a legitimate transition may advance), then lands Completed +
    docstatus 1 with a direct ``frappe.db.set_value`` — the same SYNTHETIC-row
    pattern ``apex.tests.factories.make_open_assignment`` uses. This test pins the
    utilisation engine's READ query (vehicle + status + docstatus + trip_date), not
    Dispatch Trip's own write controller or its workflow.
    """
    dt = frappe.get_doc(
        {
            "doctype": "Dispatch Trip",
            "vehicle": vehicle,
            "trip_date": trip_date,
        }
    ).insert(ignore_permissions=True)
    frappe.db.set_value(
        "Dispatch Trip", dt.name, {"status": "Completed", "docstatus": 1}
    )
    return dt.name


class TestWeeklyVehicleUtilisationSnapshot(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self.vehicle = _vehicle()
        self.addCleanup(self._purge)

    def _purge(self):
        frappe.set_user("Administrator")
        frappe.db.delete("Vehicle Utilisation Snapshot", {"vehicle": self.vehicle})
        frappe.db.delete("Dispatch Trip", {"vehicle": self.vehicle})
        frappe.db.delete("Salis Vehicle", {"name": self.vehicle})

    def test_snapshot_derives_trip_count_idle_days_and_utilisation_pct(self):
        # Two distinct days, each with one completed trip, inside the trailing
        # 7-day window (today and today-2).
        _completed_trip(self.vehicle, today())
        _completed_trip(self.vehicle, add_days(today(), -2))

        weekly_vehicle_utilisation_snapshot()

        row = frappe.db.get_value(
            "Vehicle Utilisation Snapshot",
            {"vehicle": self.vehicle, "snapshot_date": today()},
            ["trips_count", "idle_days", "utilisation_pct", "period_days"],
            as_dict=True,
        )
        self.assertIsNotNone(row, "a snapshot row must be written for the vehicle")
        self.assertEqual(row.period_days, 7)
        self.assertEqual(row.trips_count, 2)
        # 2 of 7 window days had a trip -> 5 idle days, 28.57% utilisation.
        self.assertEqual(row.idle_days, 5)
        self.assertEqual(row.utilisation_pct, round(2 / 7 * 100, 2))

    def test_snapshot_is_idempotent_on_vehicle_and_date(self):
        weekly_vehicle_utilisation_snapshot()
        first_count = frappe.db.count(
            "Vehicle Utilisation Snapshot",
            {"vehicle": self.vehicle, "snapshot_date": today()},
        )
        weekly_vehicle_utilisation_snapshot()
        second_count = frappe.db.count(
            "Vehicle Utilisation Snapshot",
            {"vehicle": self.vehicle, "snapshot_date": today()},
        )
        self.assertEqual(first_count, 1)
        self.assertEqual(second_count, 1)
