"""Tests for the Fuel Quota per-vehicle-per-period uniqueness guard."""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase


class TestFuelQuotaUniqueness(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self.vehicle = (
            frappe.get_doc(
                {
                    "doctype": "Salis Vehicle",
                    "plate_number": f"FQ {frappe.generate_hash(length=6)}",
                    "status": "Active",
                }
            )
            .insert(ignore_permissions=True)
            .name
        )
        self.period = "2026-05"

    def _quota(self, period=None):
        return frappe.get_doc(
            {
                "doctype": "Fuel Quota",
                "vehicle": self.vehicle,
                "period_month": period or self.period,
                "monthly_litres": 100,
            }
        ).insert(ignore_permissions=True)

    def test_duplicate_vehicle_period_is_rejected(self):
        # First quota is fine; a second for the same vehicle + period double-allocates.
        self._quota()
        with self.assertRaises(frappe.ValidationError):
            self._quota()

    def test_different_period_is_allowed(self):
        # Non-vacuous: the guard is scoped to the period, not the vehicle.
        self._quota("2026-05")
        other = self._quota("2026-06")
        self.assertTrue(other.name)
