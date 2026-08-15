# Copyright (c) 2026, AFMCO and contributors
"""Night-shift midnight boundary tests for the Masar trip resolvers (R4).

A worker shuttle that departs before midnight runs past it: at 00:05 the trip's
``trip_date`` is still yesterday. A ``trip_date = today()`` filter dropped that
trip at the exact moment the worker needed to board (and the driver route view
lost it too). The resolvers now span a yesterday+today window and drop only a
yesterday trip that has already finished, so an in-motion night run stays
reachable without resurrecting a completed one.

These are pure-logic tests: ``frappe.get_all`` is patched to capture the filter
dict the resolver builds and to feed back synthetic trips, so the boundary logic
is exercised deterministically without a live bench (no DB rows are created).
"""

from __future__ import annotations

from unittest.mock import patch

from frappe.tests.utils import FrappeTestCase

from apex.salis.api import masar


def _captured_filters(calls, doctype):
    """The filters dict from the first patched get_all call for ``doctype``."""
    for c in calls:
        if c.args and c.args[0] == doctype:
            return c.kwargs.get("filters") or (c.args[1] if len(c.args) > 1 else {})
    return None


class TestMasarNightShiftWindow(FrappeTestCase):
    def test_today_worker_trips_window_spans_yesterday_and_today(self):
        from frappe.utils import add_days, today

        with patch("apex.salis.api.masar.frappe.get_all", return_value=[]) as g:
            masar._today_worker_trips("DRV-TEST")
        filters = _captured_filters(g.mock_calls, "Dispatch Trip")
        self.assertIsNotNone(filters)
        td = filters["trip_date"]
        self.assertEqual(td[0], "in")
        self.assertIn(today(), td[1])
        self.assertIn(add_days(today(), -1), td[1])

    def test_worker_today_dispatch_trip_window_and_excludes_finished(self):
        from frappe.utils import add_days, today

        with patch("apex.salis.api.masar.frappe.get_all", return_value=[]) as g:
            masar._worker_today_dispatch_trip("EMP-TEST")
        filters = _captured_filters(g.mock_calls, "Dispatch Trip")
        self.assertIsNotNone(filters)
        td = filters["trip_date"]
        self.assertEqual(td[0], "in")
        self.assertIn(today(), td[1])
        self.assertIn(add_days(today(), -1), td[1])
        status = filters["status"]
        self.assertEqual(status[0], "not in")
        self.assertIn("Completed", status[1])
        self.assertIn("Cancelled", status[1])

    def test_drop_finished_yesterday_keeps_inmotion_night_run(self):
        from frappe.utils import add_days, today

        yest = add_days(today(), -1)
        trips = [
            {"name": "DT-NIGHT", "trip_date": yest, "status": "Dispatched"},
            {"name": "DT-DONE", "trip_date": yest, "status": "Completed"},
            {"name": "DT-CXL", "trip_date": yest, "status": "Cancelled"},
        ]
        kept = {t["name"] for t in masar._drop_finished_yesterday(trips)}
        self.assertEqual(kept, {"DT-NIGHT"})

    def test_drop_finished_yesterday_keeps_todays_completed_trip(self):
        from frappe.utils import today

        trips = [
            {"name": "DT-TODAY-DONE", "trip_date": today(), "status": "Completed"},
            {"name": "DT-TODAY-PLAN", "trip_date": today(), "status": "Planned"},
        ]
        kept = {t["name"] for t in masar._drop_finished_yesterday(trips)}
        self.assertEqual(kept, {"DT-TODAY-DONE", "DT-TODAY-PLAN"})
