# Copyright (c) 2026, AFMCO and contributors
"""Tests for the Vehicle Damage Write-Off controller.

Proves the escalation back-link: submitting a write-off raised from a Vehicle
Incident stamps the case onto the incident's read_only write_off_case, and
cancelling clears it, keeping the Incident<->Write-Off link bidirectional.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today


class TestVehicleDamageWriteOff(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        tag = self._testMethodName
        self.vehicle = frappe.get_doc(
            {
                "doctype": "Salis Vehicle",
                "plate_number": f"WO {tag}",
                "status": "Active",
            }
        ).insert(ignore_permissions=True).name
        self.incident = frappe.get_doc(
            {
                "doctype": "Vehicle Incident",
                "incident_type": "Accident",
                "vehicle": self.vehicle,
                "incident_date": today(),
                "description": "Test incident",
                "fault": "Third party",
            }
        ).insert(ignore_permissions=True).name

    def _write_off(self, **overrides):
        data = {
            "doctype": "Vehicle Damage Write-Off",
            "vehicle": self.vehicle,
            "source_incident": self.incident,
            "estimated_cost": 1000,
            "evidence": "/files/evidence.pdf",
        }
        data.update(overrides)
        return frappe.get_doc(data).insert(ignore_permissions=True)

    def test_submit_stamps_back_link_on_source_incident(self):
        case = self._write_off()
        self.assertFalse(
            frappe.db.get_value("Vehicle Incident", self.incident, "write_off_case"),
            "the back-link must be empty before submit",
        )
        case.submit()
        self.assertEqual(
            frappe.db.get_value("Vehicle Incident", self.incident, "write_off_case"),
            case.name,
            "submit must stamp the case onto the incident's write_off_case",
        )

    def test_cancel_clears_back_link(self):
        case = self._write_off()
        case.submit()
        case.cancel()
        self.assertFalse(
            frappe.db.get_value("Vehicle Incident", self.incident, "write_off_case"),
            "cancel must clear the incident's write_off_case",
        )

    def test_submit_without_source_incident_is_noop(self):
        case = self._write_off(source_incident=None)
        case.submit()
        self.assertFalse(
            frappe.db.get_value("Vehicle Incident", self.incident, "write_off_case"),
            "an unrelated incident must not be touched when no source_incident is set",
        )

    def test_negative_estimated_cost_is_rejected(self):
        # a negative estimated cost is never a valid write-off amount.
        with self.assertRaises(frappe.ValidationError):
            self._write_off(estimated_cost=-1)

    def test_non_negative_estimated_cost_is_allowed(self):
        # Non-vacuous: the guard rejects only negatives; zero and positive pass.
        zero = self._write_off(estimated_cost=0)
        self.assertTrue(zero.name)
        positive = self._write_off(estimated_cost=500)
        self.assertTrue(positive.name)
