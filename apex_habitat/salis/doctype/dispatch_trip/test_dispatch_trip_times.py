# Copyright (c) 2026, AFMCO and contributors
"""Tests for the Dispatch Trip return/depart time-order guard (T-706).

The guard only fires on a Completed trip with BOTH times set; a return earlier
than the depart is rejected, equal/later is accepted. Planned trips are exempt
(a freshly created trip carries an auto-filled nowtime that would false-positive).
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

test_ignore = ["Salis Vehicle", "Salis Driver", "Route Plan", "Transport Request", "Payment Gateway"]


def _trip(status, depart, ret):
    # Build an unsaved controller and run only the time guard — isolates the rule
    # under test from the unrelated readiness/odometer/capacity validations.
    doc = frappe.get_doc(
        {
            "doctype": "Dispatch Trip",
            "status": status,
            "depart_time": depart,
            "return_time": ret,
        }
    )
    return doc


class TestDispatchTripTimes(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")

    def test_completed_return_before_depart_is_rejected(self):
        with self.assertRaises(frappe.ValidationError):
            _trip("Completed", "10:00:00", "08:00:00")._validate_trip_times()

    def test_completed_return_after_depart_passes(self):
        # Non-vacuous: a well-ordered Completed trip must not raise.
        _trip("Completed", "08:00:00", "10:00:00")._validate_trip_times()

    def test_completed_equal_times_pass(self):
        # Boundary: equal times are a zero-duration record, not a sequencing error.
        _trip("Completed", "09:00:00", "09:00:00")._validate_trip_times()

    def test_planned_reversed_times_are_exempt(self):
        # A Planned trip carries an auto-filled nowtime; the guard must not fire.
        _trip("Planned", "10:00:00", "08:00:00")._validate_trip_times()

    def test_completed_missing_one_time_is_exempt(self):
        # Only depart set -> incomplete pair -> guard skipped (no crash).
        _trip("Completed", "10:00:00", None)._validate_trip_times()
