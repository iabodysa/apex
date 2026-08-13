from __future__ import annotations

from datetime import date

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.patches.v2_6.migrate_masar_route_model import (
    _missing_stop_keys,
    _single_distinct,
    _trip_context_values,
)


class TestMasarRouteModelMigration(FrappeTestCase):
    def test_single_distinct_refuses_conflicting_history(self):
        self.assertEqual(_single_distinct([None, "VEH-1", "VEH-1"]), "VEH-1")
        self.assertIsNone(_single_distinct(["VEH-1", "VEH-2"]))

    def test_missing_stop_keys_are_stable_and_do_not_replace_existing_keys(self):
        rows = [
            frappe._dict(name="ROW-1", idx=1, stop_key="housing"),
            frappe._dict(name="ROW-2", idx=2, stop_key=None),
            frappe._dict(name="ROW-3", idx=3, stop_key=None),
        ]

        self.assertEqual(
            _missing_stop_keys(rows),
            {"ROW-2": "stop-2", "ROW-3": "stop-3"},
        )

    def test_trip_context_backfill_never_overwrites_live_values(self):
        trip = frappe._dict(
            trip_title=None,
            trip_date=date(2026, 8, 13),
            transport_request="TR-LIVE",
            route_assignment=None,
            route_template=None,
            project=None,
            vehicle="VEH-LIVE",
            driver=None,
            shift_name=None,
        )
        plan = frappe._dict(
            route_name="Morning Shuttle",
            transport_request="TR-OLD",
            route_assignment="RA-1",
            project="PROJ-1",
            vehicle="VEH-OLD",
            driver="DRV-1",
            shift="Morning",
        )
        assignment = frappe._dict(route_template="RT-1", shift_name="Early")

        self.assertEqual(
            _trip_context_values(trip, plan, assignment),
            {
                "trip_title": "Morning Shuttle · 2026-08-13",
                "route_assignment": "RA-1",
                "route_template": "RT-1",
                "project": "PROJ-1",
                "driver": "DRV-1",
                "shift_name": "Early",
            },
        )
