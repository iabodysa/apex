# Copyright (c) 2026, AFMCO and contributors
"""Tests for the workshop-overstay rule shared by the alert and the number card.

``_overstay_stops`` is the one place the rule lives (day cutoff + still out of
service), so both ``workshop_overstay_watch`` and ``get_workshop_overstay_count``
read the same answer -- this pins that rule directly: a vehicle back Active is
excluded even with an unreturned Maintenance stop, and a stop inside the grace
window is excluded even for a vehicle still Stopped.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today

from apex.salis.tasks.workshop import _overstay_stops


def _vehicle(status="Stopped"):
    doc = frappe.get_doc(
        {
            "doctype": "Salis Vehicle",
            "plate_number": "_T564 " + frappe.generate_hash(length=8),
        }
    ).insert(ignore_permissions=True)
    frappe.db.set_value("Salis Vehicle", doc.name, "status", status)
    return doc.name


def _stop(vehicle, stop_date, submit=True, reason="Maintenance"):
    doc = frappe.get_doc(
        {
            "doctype": "Vehicle Suspension",
            "vehicle": vehicle,
            "stop_reason": reason,
            "stop_date": stop_date,
        }
    ).insert(ignore_permissions=True)
    if submit:
        doc.submit()
    return doc.name


class TestOverstayStops(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")

    def test_stop_past_the_cutoff_on_a_still_stopped_vehicle_is_included(self):
        vehicle = _vehicle("Stopped")
        name = _stop(vehicle, add_days(today(), -20))

        stops = _overstay_stops()

        self.assertIn(name, [r.name for r in stops])

    def test_stop_inside_the_grace_window_is_excluded(self):
        vehicle = _vehicle("Stopped")
        name = _stop(vehicle, add_days(today(), -1))

        stops = _overstay_stops()

        self.assertNotIn(name, [r.name for r in stops])

    def test_vehicle_returned_to_active_is_excluded_even_with_an_unreturned_stop(self):
        """The join is on the vehicle's CURRENT status, not the suspension row alone."""
        vehicle = _vehicle("Stopped")
        name = _stop(vehicle, add_days(today(), -20))
        frappe.db.set_value("Salis Vehicle", vehicle, "status", "Active")

        stops = _overstay_stops()

        self.assertNotIn(name, [r.name for r in stops])

    def test_a_returned_suspension_is_excluded(self):
        vehicle = _vehicle("Stopped")
        doc = frappe.get_doc(
            {
                "doctype": "Vehicle Suspension",
                "vehicle": vehicle,
                "stop_reason": "Maintenance",
                "stop_date": add_days(today(), -20),
                "return_date": today(),
            }
        ).insert(ignore_permissions=True)
        doc.submit()

        stops = _overstay_stops()

        self.assertNotIn(doc.name, [r.name for r in stops])

    def test_a_draft_suspension_is_excluded(self):
        vehicle = _vehicle("Stopped")
        name = _stop(vehicle, add_days(today(), -20), submit=False)

        stops = _overstay_stops()

        self.assertNotIn(name, [r.name for r in stops])
