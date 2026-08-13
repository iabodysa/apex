from unittest import TestCase
from unittest.mock import MagicMock, patch

import frappe

from apex.apex_core.utils.portal_token_security import DRIVER, WORKER
from apex.salis.api import portal_notifications


class TestPortalNotifications(TestCase):
    @patch.object(portal_notifications.web_push, "public_key", return_value="public-key")
    @patch.object(portal_notifications.web_push, "is_configured", return_value=True)
    @patch.object(portal_notifications, "_resolve_identity", return_value=(WORKER, "EMP-1"))
    def test_config_is_available_only_after_token_identity_resolves(
        self, _identity, _configured, _public_key
    ):
        self.assertEqual(
            portal_notifications.get_config("worker"),
            {"enabled": True, "vapid_public_key": "public-key"},
        )

    @patch.object(portal_notifications.web_push, "is_allowed_push_endpoint", return_value=True)
    @patch.object(portal_notifications.web_push, "is_configured", return_value=True)
    @patch.object(portal_notifications, "_resolve_identity", return_value=(WORKER, "EMP-1"))
    @patch.object(portal_notifications.frappe, "new_doc")
    @patch.object(portal_notifications.frappe.db, "get_value", return_value=None)
    def test_subscription_is_bound_to_resolved_worker_not_client_subject(
        self, _get_value, new_doc, _identity, _configured, _allowed
    ):
        doc = MagicMock()
        new_doc.return_value = doc

        result = portal_notifications.save_subscription(
            "worker",
            "https://web.push.apple.com/example",
            "public-device-key",
            "auth-secret",
            "Mobile Safari",
        )

        values = doc.update.call_args.args[0]
        self.assertEqual(
            {key: values[key] for key in values if key != "last_seen"},
            {
                "holder_type": WORKER,
                "employee": "EMP-1",
                "driver": None,
                "endpoint": "https://web.push.apple.com/example",
                "p256dh": "public-device-key",
                "auth": "auth-secret",
                "user_agent": "Mobile Safari",
                "enabled": 1,
            },
        )
        self.assertTrue(values["last_seen"])
        doc.save.assert_called_once_with(ignore_permissions=True)
        self.assertTrue(result["subscribed"])

    @patch.object(portal_notifications.web_push, "is_allowed_push_endpoint", return_value=True)
    @patch.object(portal_notifications.web_push, "is_configured", return_value=True)
    @patch.object(portal_notifications, "_resolve_identity", return_value=(DRIVER, "DRV-1"))
    @patch.object(portal_notifications.frappe.db, "get_value")
    def test_subscription_endpoint_cannot_move_between_portal_subjects(
        self, get_value, _identity, _configured, _allowed
    ):
        get_value.return_value = frappe._dict(
            name="SUB-1",
            holder_type=WORKER,
            employee="EMP-1",
            driver=None,
        )

        with self.assertRaises(frappe.PermissionError):
            portal_notifications.save_subscription(
                "driver",
                "https://web.push.apple.com/example",
                "public-device-key",
                "auth-secret",
            )
