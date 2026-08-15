# Copyright (c) 2026, afmcoltd
"""Regression: the worker boarding resolver never reads the whole fleet's trips.

``_worker_today_dispatch_trip`` backs the worker screen's ten-second poll. It used
to read EVERY Dispatch Trip in the date window with no worker filter, then fan the
three follow-up reads out over that fleet-wide set, and only match against the
worker's own manifest in Python at the end. On a busy day that is the entire
dispatch board, six times a minute, per worker.

The worker's own requests are now resolved FIRST and every later read is keyed on
them. ``test_masar_dispatch_batch`` pins the resolver's OUTPUT across all three
trip->request links against real rows; these tests pin the SHAPE of the reads,
which output equality cannot see — a fleet-wide scan returns the same answer, just
at a cost nothing would catch.

Pure unit tests: the module's ``frappe`` handle is replaced, so no site and no rows.
"""

from __future__ import annotations

import unittest
from unittest import mock

from apex.salis.api import masar_routes


WORKER = "EMP-1"
OWN_REQUEST = "TR-1"


class _Calls:
    """Records each ``frappe.get_all`` in order, and answers it from ``by_doctype``."""

    def __init__(self, by_doctype):
        self.by_doctype = by_doctype
        self.log = []

    def __call__(self, doctype, **kwargs):
        self.log.append((doctype, kwargs))
        return self.by_doctype.get(doctype, [])

    def doctypes(self):
        return [doctype for doctype, _kwargs in self.log]

    def kwargs_for(self, doctype):
        return next(kw for dt, kw in self.log if dt == doctype)


def _run(by_doctype):
    calls = _Calls(by_doctype)
    mock_frappe = mock.MagicMock()
    mock_frappe.get_all.side_effect = calls
    mock_frappe.utils.today.return_value = "2026-08-15"
    mock_frappe.utils.add_days.return_value = "2026-08-14"
    mock_frappe.db.get_value.return_value = "BLD-1"

    with mock.patch.object(masar_routes, "frappe", mock_frappe):
        result = masar_routes._worker_today_dispatch_trip(WORKER)
    return result, calls


class TestWorkerTripReadIsWorkerScoped(unittest.TestCase):
    def test_the_worker_is_resolved_before_any_trip_is_read(self):
        _result, calls = _run(
            {
                "Transport Request Worker": [
                    {"parent": OWN_REQUEST, "pickup_point": "PICK-1"}
                ],
                "Dispatch Trip": [
                    {"name": "DT-1", "route_plan": None, "transport_request": OWN_REQUEST}
                ],
            }
        )
        read = calls.doctypes()
        self.assertIn("Dispatch Trip", read)
        self.assertLess(
            read.index("Transport Request Worker"),
            read.index("Dispatch Trip"),
            "the trip read must come after the worker is known, or it cannot be narrowed",
        )

    def test_the_trip_read_is_constrained_to_the_workers_own_requests(self):
        _result, calls = _run(
            {
                "Transport Request Worker": [
                    {"parent": OWN_REQUEST, "pickup_point": "PICK-1"}
                ],
                "Dispatch Trip": [
                    {"name": "DT-1", "route_plan": None, "transport_request": OWN_REQUEST}
                ],
            }
        )
        kwargs = calls.kwargs_for("Dispatch Trip")
        or_filters = kwargs.get("or_filters")
        self.assertTrue(
            or_filters,
            "the Dispatch Trip read carries no worker narrowing — it scans the fleet",
        )
        self.assertIn(["transport_request", "in", [OWN_REQUEST]], or_filters)

    def test_the_child_reads_are_keyed_on_the_worker_not_on_the_trip_set(self):
        _result, calls = _run(
            {
                "Transport Request Worker": [
                    {"parent": OWN_REQUEST, "pickup_point": "PICK-1"}
                ],
                "Dispatch Trip": [],
            }
        )
        assigned = calls.kwargs_for("Dispatch Trip Assigned Request")["filters"]
        self.assertEqual(["in", [OWN_REQUEST]], assigned["transport_request"])
        self.assertNotIn(
            "parent", assigned, "keying on the trip set is what made this fleet-wide"
        )
        plans = calls.kwargs_for("Route Plan")["filters"]
        self.assertEqual(["in", [OWN_REQUEST]], plans["transport_request"])

    def test_a_worker_on_no_request_reads_no_trips_at_all(self):
        result, calls = _run({"Transport Request Worker": []})
        self.assertIsNone(result)
        self.assertEqual(
            ["Transport Request Worker"],
            calls.doctypes(),
            "a worker on nothing must cost exactly one read",
        )

    def test_an_empty_link_set_is_never_sent_as_an_empty_in_clause(self):
        """frappe renders ``in []`` as ``ifnull(col,'') in ('')`` — it MATCHES nulls.

        Sending an empty list for the assigned-request or route-plan clause would
        widen the read to every trip with that column unset, i.e. undo the fix while
        still looking narrowed.
        """
        _result, calls = _run(
            {
                "Transport Request Worker": [
                    {"parent": OWN_REQUEST, "pickup_point": "PICK-1"}
                ],
                "Dispatch Trip Assigned Request": [],
                "Route Plan": [],
                "Dispatch Trip": [],
            }
        )
        for clause in calls.kwargs_for("Dispatch Trip")["or_filters"]:
            self.assertTrue(clause[2], f"empty in-clause sent: {clause}")


if __name__ == "__main__":
    unittest.main()
