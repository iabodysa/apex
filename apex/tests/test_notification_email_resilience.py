# Copyright (c) 2026, AFMCO and contributors
"""A-001 — Notification body + email-send resilience.

Two defects fixed here, both proven end-to-end:

1. EMPTY BODIES: every ``is_standard`` Notification ships ``message_type: HTML``
   but no companion ``<name>.html`` on disk, so ``Notification.get_template()``
   returned ``None`` and the rendered body was silently empty (the JSON inline
   ``message`` is discarded for standard notifications — see
   ``Notification.load_standard_properties`` -> ``get_template``). Every app
   Notification now carries the matching ``.html`` template, so
   ``get_template()`` returns a non-empty body.

2. THE CRASH / SILENT BELL: core ``send_notification_by_channel`` runs the email
   transport first inside one ``try`` and only afterwards creates the in-app
   System Notification. On a site with no default outgoing Email Account,
   ``frappe.sendmail`` raises, the handler logs "Failed to send Notification",
   AND the System Notification block that follows never runs. The app override
   ``apex.apex_core.overrides.notification.ApexNotification`` delivers the in-app
   System Notification FIRST and swallows a subsequent email failure when that
   fallback succeeded — so the bell works and no error is logged.

The email path is simulated by patching ``frappe.sendmail`` to raise, exactly
as a missing outgoing Email Account does at runtime.
"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.tests._helpers import _user

ISSUED = "Salis - Driver Clearance Issued"
BLOCKED = "Salis - Blocked Driver Clearance"
APP_MODULES = ("Salis", "Habitat", "Apex Core")


class TestNotificationEmailResilience(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.driver_user = _user("a001_driver@example.com", "Fleet Supervisor")

    def setUp(self):
        frappe.set_user("Administrator")

    def tearDown(self):
        frappe.set_user("Administrator")

    # helpers

    def _driver(self):
        name = "A001 Driver " + frappe.generate_hash(length=12)
        return frappe.get_doc(
            {"doctype": "Salis Driver", "full_name": name, "status": "Active"}
        ).insert(ignore_permissions=True).name

    def _clearance(self):
        """A draft Driver Clearance with driver_user pointed at the test user so
        the notification resolves a recipient."""
        dc = frappe.get_doc(
            {
                "doctype": "Driver Clearance",
                "driver": self._driver(),
                "clearance_reason": "End of Assignment",
                "vehicle_returned": 1,
                "fuel_chip_returned": 1,
                "custody_returned": 1,
                "status": "Open",
            }
        ).insert(ignore_permissions=True)
        # fetch_from(driver.driver_user) leaves it empty on a userless driver;
        # set it in memory for the recipient resolution the fire performs.
        dc.driver_user = self.driver_user
        return dc

    def _fire_with_no_email_account(self, notification_name, dc):
        """Fire the notification with the outgoing mail transport unavailable,
        returning (error_logs_before, error_logs_after, system_logs)."""
        before = frappe.db.count(
            "Error Log",
            {"reference_doctype": "Notification", "method": ("like", "%Failed to send%")},
        )
        notification = frappe.get_doc("Notification", notification_name)
        with patch("frappe.sendmail", side_effect=Exception("No default outgoing email account")):
            notification.send(dc)
        after = frappe.db.count(
            "Error Log",
            {"reference_doctype": "Notification", "method": ("like", "%Failed to send%")},
        )
        system_logs = frappe.get_all(
            "Notification Log",
            filters={"document_type": "Driver Clearance", "document_name": dc.name},
            fields=["name", "email_content", "subject"],
        )
        return before, after, system_logs

    # ---- defect 1: every standard notification renders a non-empty body --

    def test_all_standard_notifications_have_renderable_body(self):
        """grep-proof, at runtime: no app is_standard Notification renders empty."""
        names = frappe.get_all(
            "Notification",
            filters={"is_standard": 1, "module": ("in", APP_MODULES)},
            pluck="name",
        )
        self.assertTrue(names, "no app standard notifications found on site")
        empty = []
        for name in names:
            body = frappe.get_doc("Notification", name).get_template()
            if not (body and body.strip()):
                empty.append(name)
        self.assertEqual(empty, [], f"standard notifications with empty body: {empty}")

    # ---- defect 2: email failure does not log an error nor silence the bell

    def test_driver_clearance_issued_resilient_without_email_account(self):
        dc = self._clearance()
        before, after, system_logs = self._fire_with_no_email_account(ISSUED, dc)

        # No "Failed to send Notification" error was logged.
        self.assertEqual(after, before, "email failure logged a hard error despite the system fallback")
        # The in-app System Notification was delivered with a non-empty body.
        self.assertTrue(system_logs, "no in-app System Notification created")
        self.assertTrue(
            system_logs[0].email_content and system_logs[0].email_content.strip(),
            "System Notification body is empty",
        )

    def test_blocked_driver_clearance_resilient_without_email_account(self):
        dc = self._clearance()
        before, after, system_logs = self._fire_with_no_email_account(BLOCKED, dc)
        self.assertEqual(after, before, "email failure logged a hard error despite the system fallback")
        self.assertTrue(system_logs, "no in-app System Notification created")
        self.assertTrue(
            system_logs[0].email_content and system_logs[0].email_content.strip(),
            "System Notification body is empty",
        )
