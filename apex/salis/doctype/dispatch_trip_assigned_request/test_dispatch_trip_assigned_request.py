# Copyright (c) 2026, AFMCO and contributors
"""Tests for the Dispatch Trip Assigned Request child row.

Skeleton child; it is exercised in its real parent context — a draft Dispatch
Trip's ``assigned_requests`` table. A vehicle-less draft skips the seat-capacity
guard and the workflow side-effects, so this proves the child's columns
(transport_request / pickup_stop / dropoff_stop / requested_count / purpose)
persist and read back through the parent.

The stop columns are not decorative: ``trip_manifest.validate_request_stop_mappings``
refuses a row whose pickup or drop-off is missing or is not a ``stop_key`` on the
parent trip, so the parent carries the two stops the row names. Requires a live site."""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase


class TestDispatchTripAssignedRequest(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")

    def test_assigned_request_row_round_trips(self):
        trip = frappe.new_doc("Dispatch Trip")
        trip.naming_series = "DT-.######"
        trip.status = "Planned"
        trip.trip_date = frappe.utils.today()
        trip.append("stops", {"stop_key": "pickup", "stop_name": "Housing Gate"})
        trip.append("stops", {"stop_key": "dropoff", "stop_name": "Project Site"})
        trip.append(
            "assigned_requests",
            {
                "transport_request": "TR-FAKE-1",
                "pickup_stop": "pickup",
                "dropoff_stop": "dropoff",
                "requested_count": 4,
                "purpose": "Site shuttle",
            },
        )
        # Vehicle-less draft: capacity guard is skipped; ignore_links lets the
        # placeholder transport_request stand in without a real linked record.
        trip.insert(ignore_permissions=True, ignore_links=True)

        reloaded = frappe.get_doc("Dispatch Trip", trip.name)
        self.assertEqual(len(reloaded.assigned_requests), 1)
        row = reloaded.assigned_requests[0]
        self.assertEqual(row.transport_request, "TR-FAKE-1")
        self.assertEqual(row.pickup_stop, "pickup")
        self.assertEqual(row.dropoff_stop, "dropoff")
        self.assertEqual(row.requested_count, 4)
        self.assertEqual(row.purpose, "Site shuttle")
