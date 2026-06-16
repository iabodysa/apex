"""Tests for the Vehicle Incident controller.

Proves the theft side effects and their reversal, that an accident records the
event without touching vehicle state, and that a future-dated incident is
rejected.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today


class TestVehicleIncident(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        # [#6u8wvq]
        # [#2ciqiy]
        # [#1wxuaa]
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
        # [#t32yoo]
        inc.reload()
        self.assertEqual(inc.previous_vehicle_status, "Active")
        self.assertEqual(inc.previous_driver, self.driver)

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
