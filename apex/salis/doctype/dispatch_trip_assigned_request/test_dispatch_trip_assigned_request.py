# Copyright (c) 2026, AFMCO and contributors
"""Tests for the Dispatch Trip Assigned Request child row.

Skeleton child; it is exercised in its real parent context — a draft Dispatch
Trip's ``assigned_requests`` table. A vehicle-less draft skips the seat-capacity
guard and the workflow side-effects, so this proves the child's columns
(transport_request / requested_count / purpose) persist and read back through
the parent. Requires a live site."""

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
        trip.append(
            "assigned_requests",
            {"transport_request": "TR-FAKE-1", "requested_count": 4, "purpose": "Site shuttle"},
        )
        # Vehicle-less draft: capacity guard is skipped; ignore_links lets the
        # placeholder transport_request stand in without a real linked record.
        trip.insert(ignore_permissions=True, ignore_links=True)

        reloaded = frappe.get_doc("Dispatch Trip", trip.name)
        self.assertEqual(len(reloaded.assigned_requests), 1)
        row = reloaded.assigned_requests[0]
        self.assertEqual(row.transport_request, "TR-FAKE-1")
        self.assertEqual(row.requested_count, 4)
        self.assertEqual(row.purpose, "Site shuttle")
