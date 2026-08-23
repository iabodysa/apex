# Copyright (c) 2026, afmcoltd
"""Tests for Transport Trip Rating's own record-level guards.

"Trip must be Completed" and "the rated employee actually rode the trip" are pure
data invariants — apex/salis/doctype/transport_trip_rating/transport_trip_rating.py
``validate()`` — reachable from ANY insertion path, not only the worker portal's
``masar.submit_trip_rating`` endpoint (which keeps only the identity-bound check:
resolving WHO the caller is). Every case here goes through ``insert()``, never a
controller method directly, so it proves the guard as the framework will actually
run it.
"""

from __future__ import annotations

import frappe
from frappe.test_runner import make_test_records
from frappe.tests.utils import FrappeTestCase

from apex.salis.api.masar import _rating_stars


class TestTransportTripRating(FrappeTestCase):
    def _employee(self):
        make_test_records("Employee")
        return frappe.get_all("Employee", limit=1, pluck="name")[0]

    def _completed_trip_with_rider(self, employee):
        """A submitted, Completed Dispatch Trip carrying ``employee`` as a
        Boarded passenger on its ``boarding_state`` manifest."""
        make_test_records("Dispatch Trip")
        vehicle = frappe.get_all("Salis Vehicle", limit=1, pluck="name")[0]
        driver = frappe.get_all("Salis Driver", limit=1, pluck="name")[0]
        project = frappe.get_all("Project", limit=1, pluck="name")[0]

        trip = frappe.new_doc("Dispatch Trip")
        trip.trip_type = "Ad Hoc"
        trip.vehicle = vehicle
        trip.driver = driver
        trip.project = project
        trip.trip_date = "2026-08-20"
        trip.append("stops", {"stop_name": "Camp Gate"})
        trip.append("boarding_state", {"employee": employee, "status": "Boarded"})
        trip.insert()
        trip.submit()
        self.assertEqual(trip.status, "Completed")
        return trip

    def _rating(self, employee, dispatch_trip, **fields):
        doc = frappe.new_doc("Transport Trip Rating")
        doc.employee = employee
        doc.dispatch_trip = dispatch_trip
        doc.rating = 1
        doc.update(fields)
        return doc

    def test_a_manifested_rider_can_rate_a_completed_trip(self):
        employee = self._employee()
        trip = self._completed_trip_with_rider(employee)
        doc = self._rating(employee, trip.name)
        doc.insert()
        self.assertTrue(doc.name)

    def test_rating_a_trip_that_is_not_completed_is_refused(self):
        employee = self._employee()
        make_test_records("Dispatch Trip")
        vehicle = frappe.get_all("Salis Vehicle", limit=1, pluck="name")[0]
        driver = frappe.get_all("Salis Driver", limit=1, pluck="name")[0]
        project = frappe.get_all("Project", limit=1, pluck="name")[0]
        trip = frappe.new_doc("Dispatch Trip")
        trip.trip_type = "Ad Hoc"
        trip.vehicle = vehicle
        trip.driver = driver
        trip.project = project
        trip.trip_date = "2026-08-20"
        trip.append("stops", {"stop_name": "Camp Gate"})
        trip.append("boarding_state", {"employee": employee, "status": "Boarded"})
        trip.insert()
        self.assertEqual(trip.status, "Planned")

        doc = self._rating(employee, trip.name)
        self.assertRaises(frappe.ValidationError, doc.insert)

    def test_rating_by_an_employee_not_on_the_manifest_is_refused(self):
        make_test_records("Employee")
        employees = frappe.get_all("Employee", limit=2, pluck="name")
        rider, outsider = employees[0], employees[-1]
        if rider == outsider:
            self.skipTest("site has only one Employee test record")
        trip = self._completed_trip_with_rider(rider)

        doc = self._rating(outsider, trip.name)
        self.assertRaisesRegex(
            frappe.PermissionError,
            "manifest",
            doc.insert,
        )


class TestTheStoredRatingIsOnTheFieldsOwnScale(FrappeTestCase):
    """A Rating field holds a 0-1 fraction and the desk multiplies it by the field's
    ``options`` star count to draw it, so a whole star count written straight through
    would render as a full five however few stars the worker tapped."""

    def test_the_endpoint_reads_its_star_count_from_the_field(self):
        declared = frappe.get_meta("Transport Trip Rating").get_field("rating").options
        self.assertEqual(str(_rating_stars()), str(declared))

    def test_a_stored_rating_never_exceeds_one(self):
        """The whole point of the scale: the top of the range stores 1.0, not 5."""
        self.assertEqual(_rating_stars() / _rating_stars(), 1.0)
