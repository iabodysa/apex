# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase


def _vehicle(status="Active"):
    return frappe.get_doc(
        {
            "doctype": "Salis Vehicle",
            "plate_number": "_T-SUS " + frappe.generate_hash(length=6),
            "status": status,
        }
    ).insert(ignore_permissions=True).name


def _suspension(vehicle, **overrides):
    fields = {
        "doctype": "Vehicle Suspension",
        "vehicle": vehicle,
        "stop_reason": "Maintenance",
        "stop_date": frappe.utils.today(),
    }
    fields.update(overrides)
    return frappe.get_doc(fields)


class TestVehicleSuspensionEvidence(FrappeTestCase):
    def test_an_accident_stop_without_evidence_cannot_be_submitted(self):
        doc = _suspension(_vehicle(), stop_reason="Accident").insert(ignore_permissions=True)
        with self.assertRaisesRegex(frappe.ValidationError, "Evidence is required"):
            doc.submit()

    def test_a_violation_stop_without_evidence_cannot_be_submitted(self):
        doc = _suspension(_vehicle(), stop_reason="Violation").insert(ignore_permissions=True)
        with self.assertRaisesRegex(frappe.ValidationError, "Evidence is required"):
            doc.submit()

    def test_a_maintenance_stop_needs_no_evidence(self):
        doc = _suspension(_vehicle()).insert(ignore_permissions=True)
        doc.submit()
        self.assertEqual(doc.docstatus, 1)


class TestVehicleSuspensionStopsTheVehicle(FrappeTestCase):
    def test_submitting_a_stop_sets_the_vehicle_stopped(self):
        vehicle = _vehicle()
        _suspension(vehicle).insert(ignore_permissions=True).submit()
        self.assertEqual(frappe.db.get_value("Salis Vehicle", vehicle, "status"), "Stopped")

    def test_the_status_the_vehicle_held_is_remembered_on_the_stop(self):
        vehicle = _vehicle()
        doc = _suspension(vehicle).insert(ignore_permissions=True)
        doc.submit()
        doc.reload()
        self.assertEqual(doc.previous_status, "Active")


class TestVehicleSuspensionRelease(FrappeTestCase):
    def test_cancelling_the_only_stop_returns_the_vehicle_to_what_it_was(self):
        vehicle = _vehicle()
        doc = _suspension(vehicle).insert(ignore_permissions=True)
        doc.submit()
        doc.cancel()
        self.assertEqual(frappe.db.get_value("Salis Vehicle", vehicle, "status"), "Active")

    def test_a_vehicle_under_a_second_stop_stays_stopped(self):
        vehicle = _vehicle()
        first = _suspension(vehicle).insert(ignore_permissions=True)
        first.submit()
        second = _suspension(vehicle).insert(ignore_permissions=True)
        second.submit()
        first.cancel()
        self.assertEqual(frappe.db.get_value("Salis Vehicle", vehicle, "status"), "Stopped")
