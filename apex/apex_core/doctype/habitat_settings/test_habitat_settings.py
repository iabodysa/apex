# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase


class TestHabitatSettingsTargetPaymentDoctype(FrappeTestCase):
    def test_setting_target_payment_doctype_to_a_single_doctype_is_refused(self):
        doc = frappe.get_single("Habitat Settings")
        doc.custody_integration_mode = "Habitat Internal / No Financial Posting"
        doc.target_payment_doctype = "Habitat Settings"
        with self.assertRaises(frappe.ValidationError):
            doc.save(ignore_permissions=True)


class TestHabitatSettingsFieldMap(FrappeTestCase):
    def test_mapping_the_same_target_field_twice_is_refused(self):
        doc = frappe.get_single("Habitat Settings")
        doc.custody_integration_mode = "Habitat Internal / No Financial Posting"
        doc.target_payment_doctype = None
        doc.set("field_map", [])
        doc.append(
            "field_map",
            {"target_fieldname": "mode_of_payment", "is_static": 1, "static_value": "Cash"},
        )
        doc.append(
            "field_map",
            {"target_fieldname": "mode_of_payment", "is_static": 1, "static_value": "Bank"},
        )
        with self.assertRaisesRegex(frappe.ValidationError, "mapped more than once"):
            doc.save(ignore_permissions=True)


class TestHabitatSettingsBackdatingRole(FrappeTestCase):
    def test_a_backdating_role_with_zero_days_warns_without_blocking_the_save(self):
        doc = frappe.get_single("Habitat Settings")
        doc.custody_integration_mode = "Habitat Internal / No Financial Posting"
        doc.target_payment_doctype = None
        doc.set("field_map", [])
        doc.backdating_role = "System Manager"
        doc.backdating_days = 0
        frappe.clear_messages()
        doc.save(ignore_permissions=True)
        messages = " ".join(m.get("message", "") for m in frappe.get_message_log())
        self.assertIn("no effect while the window is zero days", messages)
