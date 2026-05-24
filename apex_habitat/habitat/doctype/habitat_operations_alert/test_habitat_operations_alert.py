"""Tests for Habitat Operations Alert."""

import frappe
import unittest


class TestHabitatOperationsAlert(unittest.TestCase):
    def test_create_alert(self):
        from apex_habitat.habitat.doctype.habitat_operations_alert.habitat_operations_alert import create_alert
        create_alert(
            alert_type="General",
            message="Test alert message",
            severity="Info",
        )
        # Verify the alert was created
        alerts = frappe.get_all(
            "Habitat Operations Alert",
            filters={"message": "Test alert message"},
            fields=["name", "severity", "is_resolved"],
        )
        self.assertTrue(len(alerts) > 0)
        self.assertEqual(alerts[0]["severity"], "Info")
        self.assertEqual(alerts[0]["is_resolved"], 0)
