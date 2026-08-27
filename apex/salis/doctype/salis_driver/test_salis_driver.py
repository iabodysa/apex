# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase


def _driver(**overrides):
    fields = {
        "doctype": "Salis Driver",
        "full_name": "_T-SalisDriver " + frappe.generate_hash(length=6),
    }
    fields.update(overrides)
    return frappe.get_doc(fields)


def _vehicle():
    return frappe.get_doc(
        {
            "doctype": "Salis Vehicle",
            "plate_number": "_T-DRV " + frappe.generate_hash(length=6),
            "status": "Active",
        }
    ).insert(ignore_permissions=True).name


class TestSalisDriverStatusIsRecordOwned(FrappeTestCase):
    def test_a_new_driver_is_forced_active_whatever_was_typed(self):
        doc = _driver(status="Stopped").insert(ignore_permissions=True)
        self.assertEqual(doc.status, "Active")

    def test_editing_the_status_by_hand_is_refused(self):
        doc = _driver().insert(ignore_permissions=True)
        doc.status = "Stopped"
        with self.assertRaises(frappe.PermissionError):
            doc.save(ignore_permissions=True)


class TestSalisDriverPairingIsRecordOwned(FrappeTestCase):
    def test_a_new_driver_naming_a_vehicle_is_refused(self):
        doc = _driver(current_vehicle=_vehicle())
        with self.assertRaises(frappe.PermissionError):
            doc.insert(ignore_permissions=True)

    def test_editing_the_current_vehicle_by_hand_is_refused(self):
        doc = _driver().insert(ignore_permissions=True)
        doc.current_vehicle = _vehicle()
        with self.assertRaises(frappe.PermissionError):
            doc.save(ignore_permissions=True)

    def test_a_save_that_touches_neither_field_is_accepted(self):
        doc = _driver().insert(ignore_permissions=True)
        doc.license_number = "_T-LIC-1"
        doc.save(ignore_permissions=True)
        self.assertEqual(doc.license_number, "_T-LIC-1")
