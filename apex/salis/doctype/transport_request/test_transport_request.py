# Copyright (c) 2026, afmcoltd
"""What a Transport Request guarantees, asserted against the DocType itself.

``request_type`` must agree with ``service_line`` (Site Transport implies
Accommodation to Project Shuttle, and so on); an Administrative Trip may never
carry labour accommodation or a worker manifest. Each request type has its own
required fields (building+project for a shuttle, at least one worker for an
Inter-City Relocation, a destination for an Administrative Trip).
``worker_count`` is always derived from the workers table, never hand-set, and
``passenger_count`` is clamped to the 1-50 range the fleet can actually carry.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

test_dependencies = ["Building", "Project"]


class TestTransportRequest(FrappeTestCase):
    def test_a_request_type_not_valid_for_its_service_line_is_refused(self):
        """A shuttle request type on an Administrative Trip service line describes no real request."""
        request = frappe.copy_doc(frappe.get_test_records("Transport Request")[0])
        request.service_line = "Administrative Trip"
        request.request_type = "Accommodation to Project Shuttle"
        self.assertRaisesRegex(
            frappe.ValidationError,
            "is not valid for the",
            request.insert,
        )

    def test_an_administrative_trip_cannot_carry_a_worker_manifest(self):
        """A simple administrative trip is not the workforce-shuttle request type."""
        request = frappe.copy_doc(frappe.get_test_records("Transport Request")[0])
        request.append("workers", {"employee": "_T-Employee-00001"})
        self.assertRaisesRegex(
            frappe.ValidationError,
            "cannot carry a worker manifest",
            request.insert,
        )

    def test_an_administrative_trip_without_a_destination_is_refused(self):
        """An administrative trip with nowhere named is not a trip anyone can plan."""
        request = frappe.copy_doc(frappe.get_test_records("Transport Request")[0])
        request.destination = None
        self.assertRaisesRegex(
            frappe.ValidationError,
            "Destination is required",
            request.insert,
        )

    def test_a_shuttle_request_without_building_or_project_is_refused(self):
        """A shuttle with no origin building and no project bills and routes nowhere."""
        request = frappe.copy_doc(frappe.get_test_records("Transport Request")[1])
        request.accommodation_building = None
        self.assertRaisesRegex(
            frappe.ValidationError,
            "Building and Project are required",
            request.insert,
        )

    def test_worker_count_is_recomputed_from_the_workers_table(self):
        """A hand-set worker count must not survive save; it always reflects the real rows."""
        request = frappe.copy_doc(frappe.get_test_records("Transport Request")[1])
        request.worker_count = 999
        request.append("workers", {"employee": "_T-Employee-00001"})
        request.append("workers", {"employee": "_T-Employee-00002"})
        request.insert()
        self.assertEqual(request.worker_count, 2)

    def test_passenger_count_is_clamped_to_the_one_to_fifty_range(self):
        """A request for more seats than any vehicle carries must still save, clamped to the ceiling."""
        request = frappe.copy_doc(frappe.get_test_records("Transport Request")[1])
        request.passenger_count = 100
        request.insert()
        self.assertEqual(request.passenger_count, 50)
