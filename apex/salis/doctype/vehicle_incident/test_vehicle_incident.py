# Copyright (c) 2026, AFMCO and contributors
"""Tests for the Vehicle Incident controller.

Proves the theft side effects and their reversal, that an accident records the
event without touching vehicle state, and that a future-dated incident is
rejected.
"""

from __future__ import annotations

import json

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today


class TestVehicleIncident(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        # [#gn6wfx]
        tag = self._testMethodName
        self.driver = frappe.get_doc(
            {"doctype": "Salis Driver", "full_name": f"Incident Driver {tag}", "status": "Active"}
        ).insert(ignore_permissions=True).name
        self.vehicle = frappe.get_doc(
            {
                "doctype": "Salis Vehicle",
                "plate_number": f"INC {tag}",
                "status": "Active",
                "current_driver": self.driver,
            }
        ).insert(ignore_permissions=True).name

    def _incident(self, incident_type, **overrides):
        data = {
            "doctype": "Vehicle Incident",
            "incident_type": incident_type,
            "vehicle": self.vehicle,
            "incident_date": today(),
            "description": "Test incident",
        }
        data.update(overrides)
        return frappe.get_doc(data).insert(ignore_permissions=True)

    def _card_count(self, card_name):
        # [#4kynzx]
        card = frappe.get_doc("Number Card", card_name)
        return frappe.db.count(card.document_type, json.loads(card.filters_json or "[]"))

    def test_theft_stops_vehicle_and_clears_driver(self):
        inc = self._incident("Theft")
        inc.submit()
        v = frappe.get_doc("Salis Vehicle", self.vehicle)
        self.assertEqual(v.status, "Stopped")
        self.assertFalse(v.current_driver, "theft must clear the current driver")
        self.assertFalse(
            frappe.db.get_value("Salis Driver", self.driver, "current_vehicle"),
            "theft must clear the driver's current vehicle",
        )
        # [#6y3htq]
        inc.reload()
        self.assertEqual(inc.previous_status, "Active")
        self.assertEqual(inc.previous_driver, self.driver)

    def test_theft_increments_open_incident_and_theft_cards(self):
        # [#ofos3i]
        before_incidents = self._card_count("Open Vehicle Incidents")
        before_theft = self._card_count("Open Theft Reports")

        inc = self._incident("Theft")
        inc.submit()
        self.assertEqual(inc.status, "Open", "a submitted theft stays Open for the dashboard")
        self.assertEqual(
            self._card_count("Open Vehicle Incidents"),
            before_incidents + 1,
            "the Open Vehicle Incidents card must count the new theft",
        )
        self.assertEqual(
            self._card_count("Open Theft Reports"),
            before_theft + 1,
            "the Open Theft Reports card must count the new theft",
        )

        # [#s9978y]
        acc = self._incident("Accident", fault="Third party")
        acc.submit()
        self.assertEqual(
            self._card_count("Open Vehicle Incidents"),
            before_incidents + 2,
            "the general card must also count the accident",
        )
        self.assertEqual(
            self._card_count("Open Theft Reports"),
            before_theft + 1,
            "an accident must not change the theft card",
        )

    def test_cancel_theft_restores_vehicle_and_driver(self):
        inc = self._incident("Theft")
        inc.submit()
        inc.cancel()
        v = frappe.get_doc("Salis Vehicle", self.vehicle)
        self.assertEqual(v.status, "Active", "cancel must restore the prior status")
        self.assertEqual(v.current_driver, self.driver, "cancel must restore the driver")

    def test_accident_does_not_change_vehicle(self):
        inc = self._incident("Accident", fault="Third party")
        inc.submit()
        v = frappe.get_doc("Salis Vehicle", self.vehicle)
        self.assertEqual(v.status, "Active", "an accident records the event only")
        self.assertEqual(v.current_driver, self.driver)

    def test_future_dated_incident_rejected(self):
        with self.assertRaises(frappe.ValidationError):
            self._incident("Accident", incident_date=add_days(today(), 1))

    def test_negative_estimated_cost_rejected(self):
        # [#82nrhv]
        with self.assertRaises(frappe.ValidationError):
            self._incident("Accident", fault="Third party", estimated_cost=-100)

    def test_zero_or_positive_estimated_cost_allowed(self):
        # [#2qwohn]
        zero = self._incident("Accident", fault="Third party", estimated_cost=0)
        self.assertTrue(zero.name)
        positive = self._incident("Accident", fault="Third party", estimated_cost=2500)
        self.assertTrue(positive.name)
