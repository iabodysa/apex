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
