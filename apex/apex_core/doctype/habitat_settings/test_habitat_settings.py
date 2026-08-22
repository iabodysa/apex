# Copyright (c) 2026, AFMCO and contributors
import frappe
from frappe.tests.utils import FrappeTestCase

test_ignore = [
    "Additional Salary",
    "Asset",
    "Asset Movement",
    "Company",
    "Cost Center",
    "Currency",
    "Employee",
    "Item",
    "Payment Entry",
    "Project",
    "Purchase Invoice",
    "Role",
    "Salary Component",
    "Supplier",
    "User",
]


class TestHabitatSettings(FrappeTestCase):

    def test_single_doctype_loads(self):
        doc = frappe.get_single("Habitat Settings")
        self.assertEqual(doc.doctype, "Habitat Settings")

    def test_custody_integration_mode_field_exists(self):
        meta = frappe.get_meta("Habitat Settings")
        field_names = [f.fieldname for f in meta.fields]
        self.assertIn("custody_integration_mode", field_names)

    def test_set_custody_mode_in_memory(self):
        doc = frappe.get_single("Habitat Settings")
        doc.custody_integration_mode = "Habitat Internal / No Financial Posting"
        self.assertEqual(doc.custody_integration_mode, "Habitat Internal / No Financial Posting")


class TestEmailKillSwitchReachesNotifications(FrappeTestCase):
    """The switch's own promise: with it OFF the app sends no email even when an
    individual Notification record is enabled.

    A Notification reaches frappe.sendmail through core, not through any of this app's
    call sites, so email_gate.email_enabled cannot see it. ApexNotification is the one
    place every record passes through, and eighteen of the records this app ships carry
    enabled: 1 with channel Email. Asserted on the channel dispatch rather than on
    Email Queue, because a bench with no outgoing Email Account never reaches the queue
    and the test would pass for the wrong reason.
    """

    def _dispatch(self, enabled, channel="Email"):
        """Run one channel dispatch with the switch in a known state; return what was sent."""
        previous = frappe.db.get_single_value("Habitat Settings", "enable_email_notifications")
        frappe.db.set_single_value("Habitat Settings", "enable_email_notifications", enabled)
        self.addCleanup(
            frappe.db.set_single_value,
            "Habitat Settings",
            "enable_email_notifications",
            previous,
        )
        frappe.clear_cache(doctype="Habitat Settings")

        sent = []
        notification = frappe.new_doc("Notification")
        notification.channel = channel
        notification.send_system_notification = 0
        notification.send_an_email = lambda doc, context: sent.append("email")
        notification.send_notification_by_channel(frappe.new_doc("ToDo"), {})
        return sent

    def test_the_override_is_the_class_frappe_instantiates(self):
        """Without this the two tests below would grade core's class, not the app's."""
        from apex.apex_core.overrides.notification import ApexNotification

        self.assertIsInstance(frappe.new_doc("Notification"), ApexNotification)

    def test_an_enabled_notification_sends_no_email_while_the_switch_is_off(self):
        self.assertEqual(self._dispatch(0), [])

    def test_the_same_notification_sends_once_the_switch_is_on(self):
        """The control: without it, a dispatch broken in any other way would pass above."""
        self.assertEqual(self._dispatch(1), ["email"])
