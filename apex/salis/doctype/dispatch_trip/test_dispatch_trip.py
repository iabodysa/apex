# Copyright (c) 2026, afmcoltd
"""Tests for Dispatch Trip's own validation guards.

Patterned on frappe/tests/test_document.py: each case builds an unsaved
Document via frappe.new_doc and calls one guard method directly, asserting
the refusal or its absence. Nothing is inserted — every guard under test
here reads only the in-memory document, never the database.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase


class TestDispatchTrip(FrappeTestCase):
    def _trip(self, **fields):
        doc = frappe.new_doc("Dispatch Trip")
        doc.update(fields)
        return doc

    def test_odometer_start_and_end_must_be_set_together(self):
        doc = self._trip(odometer_start=100)
        self.assertRaises(frappe.ValidationError, doc._validate_odometer)

    def test_odometer_pair_left_fully_empty_is_not_a_refusal(self):
        doc = self._trip()
        doc._validate_odometer()

    def test_trip_end_odometer_cannot_be_less_than_start(self):
        doc = self._trip(odometer_start=200, odometer_end=150)
        self.assertRaises(frappe.ValidationError, doc._validate_odometer)

    def test_trip_end_odometer_equal_to_start_is_accepted(self):
        doc = self._trip(odometer_start=200, odometer_end=200)
        doc._validate_odometer()

    def test_return_time_cannot_be_earlier_than_depart_time_once_completed(self):
        doc = self._trip(
            status="Completed", depart_time="10:00:00", return_time="09:00:00"
        )
        self.assertRaises(frappe.ValidationError, doc._validate_trip_times)

    def test_reversed_times_are_not_checked_before_completion(self):
        doc = self._trip(
            status="Planned", depart_time="10:00:00", return_time="09:00:00"
        )
        doc._validate_trip_times()

    def test_a_new_trip_must_start_as_planned(self):
        doc = self._trip(status="Completed")
        self.assertTrue(doc.is_new())
        self.assertRaises(frappe.ValidationError, doc._guard_initial_status)

    def test_a_new_trip_left_at_planned_is_not_a_refusal(self):
        doc = self._trip(status="Planned")
        doc._guard_initial_status()

    def test_completion_notes_are_required_once_status_is_completed(self):
        doc = self._trip(status="Completed", completion_notes="   ")
        self.assertRaises(frappe.ValidationError, doc._require_completion_notes)

    def test_completion_notes_present_satisfies_the_completed_guard(self):
        doc = self._trip(status="Completed", completion_notes="Delivered on time.")
        doc._require_completion_notes()


class TestDispatchTripDriverPositionIsFrozenAfterSubmit(FrappeTestCase):
    """``driver_lat``/``driver_lng``/``driver_position_updated_at`` carried
    ``allow_on_submit: 1`` with no writer anywhere in the app (see
    apex/salis/api/route_supervisor.py:4-12). Removing the flag lets the framework
    refuse a post-submit edit again. Proven through ``insert()``/``submit()``/
    ``save()``, never by calling a controller method directly."""

    def _submitted_trip(self):
        from frappe.test_runner import make_test_records

        make_test_records("Dispatch Trip")
        vehicle = frappe.get_all("Salis Vehicle", limit=1, pluck="name")[0]
        driver = frappe.get_all("Salis Driver", limit=1, pluck="name")[0]
        project = frappe.get_all("Project", limit=1, pluck="name")[0]
        employee = frappe.get_all("Employee", limit=1, pluck="name")
        if not employee:
            from frappe.test_runner import make_test_records as _mtr

            _mtr("Employee")
            employee = frappe.get_all("Employee", limit=1, pluck="name")
        doc = frappe.new_doc("Dispatch Trip")
        doc.trip_type = "Ad Hoc"
        doc.vehicle = vehicle
        doc.driver = driver
        doc.project = project
        doc.trip_date = "2026-08-20"
        doc.append("stops", {"stop_name": "Camp Gate"})
        doc.append("boarding_state", {"employee": employee[0], "status": "Boarded"})
        doc.insert()
        doc.submit()
        return doc

    def test_editing_driver_lat_after_submit_is_refused(self):
        doc = self._submitted_trip()
        doc.driver_lat = 24.7
        self.assertRaises(frappe.exceptions.UpdateAfterSubmitError, doc.save)
