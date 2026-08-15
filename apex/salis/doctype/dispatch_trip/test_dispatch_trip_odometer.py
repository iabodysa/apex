# Copyright (c) 2026, AFMCO and contributors
""" regression: Dispatch Trip odometer mutual-presence guard.

Frappe stores an empty Int field as 0, so an ``odometer_end`` set while
``odometer_start`` is left at its 0 default would pass a naive ``if not start``
check and silently break distance/odometer-advance accounting on submit.
``_validate_odometer`` requires both-or-neither and end >= start.

Run with:
    bench --site <site> run-tests --app apex \
        --module apex.salis.doctype.dispatch_trip.test_dispatch_trip_odometer
"""

from __future__ import annotations

import unittest

import frappe


class TestDispatchTripOdometer(unittest.TestCase):
    def _make_trip(self, start, end):
        doc = frappe.new_doc("Dispatch Trip")
        doc.odometer_start = start
        doc.odometer_end = end
        return doc

    def test_end_set_while_start_zero_throws(self):
        doc = self._make_trip(0, 150)
        with self.assertRaises(frappe.ValidationError):
            doc._validate_odometer()

    def test_start_set_while_end_zero_throws(self):
        doc = self._make_trip(100, 0)
        with self.assertRaises(frappe.ValidationError):
            doc._validate_odometer()

    def test_end_less_than_start_throws(self):
        doc = self._make_trip(200, 150)
        with self.assertRaises(frappe.ValidationError):
            doc._validate_odometer()

    def test_both_unset_passes(self):
        doc = self._make_trip(0, 0)
        doc._validate_odometer()

    def test_valid_pair_passes(self):
        doc = self._make_trip(100, 250)
        doc._validate_odometer()
