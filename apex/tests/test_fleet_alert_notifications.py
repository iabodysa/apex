# Copyright (c) 2026, AFMCO and contributors
"""Standard Notification records for two fleet events: a Vehicle Incident
submitted as Theft, and a Workshop Overstay (Maintenance Overdue Operations
Alert raised by ``workshop_overstay_watch``).

Locks in two ``is_standard`` Notification records and proves they are synced on
a fresh site, that their firing condition gates on the intended trigger, and
that they resolve the intended role recipients. Condition gating is checked with
``frappe.safe_eval`` and recipient resolution through the real
``Notification.get_list_of_recipients`` (the calls the framework makes when the
alert fires), mirroring the existing notification test pattern.

All data is provisioned in setUp so the suite passes on a clean CI site with no
ambient rows.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today

from apex.tests._helpers import _user

THEFT_NOTIFICATION = "Salis - Vehicle Theft Reported"
OVERSTAY_NOTIFICATION = "Salis - Workshop Overstay"


def _recipients(notification_name, doc):
    notification = frappe.get_doc("Notification", notification_name)
    context = {"doc": doc, "alert": notification, "comments": None}
    recipients, _cc, _bcc = notification.get_list_of_recipients(doc, context)
    return recipients


class TestFleetAlertNotifications(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.fleet_manager = _user("fan_mgr@example.com", "Fleet Manager")
        cls.fleet_sup = _user("fan_sup@example.com", "Fleet Supervisor")
        cls.gro = _user("fan_gro@example.com", "Government Relations Officer")

    def setUp(self):
        frappe.set_user("Administrator")

    def tearDown(self):
        frappe.set_user("Administrator")

    def _vehicle(self):
        # [#g492jh]
        plate = "FAN " + frappe.generate_hash(length=12).upper()
        return frappe.get_doc(
            {"doctype": "Salis Vehicle", "plate_number": plate, "status": "Active"}
        ).insert(ignore_permissions=True).name

    def _incident(self, incident_type):
        return frappe.get_doc(
            {
                "doctype": "Vehicle Incident",
                "incident_type": incident_type,
                "vehicle": self._vehicle(),
                "incident_date": today(),
                "description": "test incident",
            }
        )

    def _overdue_alert(self, alert_type):
        return frappe.get_doc(
            {
                "doctype": "Operations Alert",
                "alert_type": alert_type,
                "severity": "Warning",
                "message": "test alert",
            }
        )

    def test_records_are_synced_and_shaped(self):
        """Both standard Notifications load on a fresh site with the expected
        trigger wiring (so migrate exports + imports them)."""
        theft = frappe.get_doc("Notification", THEFT_NOTIFICATION)
        self.assertEqual(theft.is_standard, 1)
        self.assertEqual(theft.document_type, "Vehicle Incident")
        self.assertEqual(theft.event, "Submit")
        self.assertEqual(theft.condition, 'doc.incident_type == "Theft"')
        self.assertEqual(theft.send_system_notification, 1)
        self.assertEqual(theft.enabled, 1)

        overstay = frappe.get_doc("Notification", OVERSTAY_NOTIFICATION)
        self.assertEqual(overstay.is_standard, 1)
        self.assertEqual(overstay.document_type, "Operations Alert")
        self.assertEqual(overstay.event, "New")
        self.assertEqual(overstay.condition, 'doc.alert_type == "Maintenance Overdue"')
        self.assertEqual(overstay.send_system_notification, 1)
        self.assertEqual(overstay.enabled, 1)

    def test_theft_condition_gates_on_incident_type(self):
        """The theft alert fires only for a Theft incident, not an Accident."""
        notification = frappe.get_doc("Notification", THEFT_NOTIFICATION)
        self.assertFalse(
            frappe.safe_eval(notification.condition, None, {"doc": self._incident("Accident")})
        )
        self.assertTrue(
            frappe.safe_eval(notification.condition, None, {"doc": self._incident("Theft")})
        )

    def test_theft_notifies_fleet_and_government(self):
        recipients = _recipients(THEFT_NOTIFICATION, self._incident("Theft"))
        self.assertIn(self.fleet_manager, recipients)
        self.assertIn(self.fleet_sup, recipients)
        self.assertIn(self.gro, recipients)

    def test_overstay_condition_gates_on_alert_type(self):
        """The overstay alert fires only for a Maintenance Overdue alert."""
        notification = frappe.get_doc("Notification", OVERSTAY_NOTIFICATION)
        self.assertFalse(
            frappe.safe_eval(notification.condition, None, {"doc": self._overdue_alert("Idle Vehicle")})
        )
        self.assertTrue(
            frappe.safe_eval(notification.condition, None, {"doc": self._overdue_alert("Maintenance Overdue")})
        )

    def test_overstay_notifies_fleet(self):
        recipients = _recipients(OVERSTAY_NOTIFICATION, self._overdue_alert("Maintenance Overdue"))
        self.assertIn(self.fleet_manager, recipients)
        self.assertIn(self.fleet_sup, recipients)
