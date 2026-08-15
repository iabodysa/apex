# Copyright (c) 2026, AFMCO and contributors
"""SSRF allowlist tests for the portal Web Push subscription endpoint.

The browser-supplied PushSubscription ``endpoint`` becomes a server-side POST target
in ``web_push._deliver``, so it is an SSRF sink. These tests prove the allowlist gate:
``is_allowed_push_endpoint`` admits only https:// URLs on a known push provider and
refuses internal/loopback/link-local/metadata hosts and non-https schemes; the
save-time gate in ``portal_notifications.save_subscription`` rejects a hostile endpoint
before it is ever stored. No real network call is made — delivery is never invoked here.

``portal_notifications`` is where the driver and worker portals now register a device;
the shipped ``test_portal_notifications.py`` patches ``is_allowed_push_endpoint`` to
True, so the allowlist itself and its wiring into the save are graded only here.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.apex_core.utils.portal_identity import DRIVER
from apex.salis.api import portal_notifications, web_push

_REAL_FCM = "https://fcm.googleapis.com/fcm/send/abc123:DEF456"
_REAL_APPLE = "https://web.push.apple.com/QABCDEF/notification"
_REAL_WNS = "https://db5.notify.windows.com/w/?token=AaBb"
_REAL_MOZILLA = "https://updates.push.services.mozilla.com/wpush/v2/gAAAA"

_HOSTILE = [
    "http://localhost/push",
    "https://localhost/push",
    "http://127.0.0.1/push",
    "https://127.0.0.1/push",
    "http://169.254.169.254/latest/meta-data/",
    "https://169.254.169.254/latest/meta-data/",
    "https://10.0.0.5/push",
    "https://192.168.1.10/push",
    "https://172.16.0.9/push",
    "https://[::1]/push",
    "http://fcm.googleapis.com/fcm/send/x",
    "https://fcm.googleapis.com.evil.com/x",
    "https://evil-push.apple.com/x",
    "https://evil.com/x",
    "ftp://fcm.googleapis.com/x",
    "",
]


class TestPushEndpointAllowlist(FrappeTestCase):
    def test_real_provider_endpoints_allowed(self):
        for ep in (_REAL_FCM, _REAL_APPLE, _REAL_WNS, _REAL_MOZILLA):
            self.assertTrue(
                web_push.is_allowed_push_endpoint(ep), msg=f"provider endpoint should be allowed: {ep}"
            )

    def test_hostile_endpoints_rejected(self):
        for ep in _HOSTILE:
            self.assertFalse(
                web_push.is_allowed_push_endpoint(ep), msg=f"endpoint should be rejected: {ep}"
            )


class TestSaveSubscriptionGate(FrappeTestCase):
    """``save_subscription`` rejects a hostile endpoint before any persistence."""

    def setUp(self):
        self._patches = [
            patch.object(
                portal_notifications, "_resolve_identity", return_value=(DRIVER, "DRV-0001")
            ),
            patch.object(web_push, "is_configured", return_value=True),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()

    def _save(self, endpoint):
        return portal_notifications.save_subscription(
            "driver", endpoint, "public-device-key", "auth-secret", "ua"
        )

    def test_internal_host_endpoint_is_rejected_at_save(self):
        for ep in ("http://localhost/push", "http://169.254.169.254/latest/meta-data/"):
            with patch.object(portal_notifications.frappe, "get_doc") as get_doc, patch.object(
                portal_notifications.frappe, "new_doc"
            ) as new_doc:
                with self.assertRaises(frappe.ValidationError):
                    self._save(ep)
                get_doc.assert_not_called()
                new_doc.assert_not_called()

    def test_non_https_endpoint_is_rejected_at_save(self):
        with self.assertRaises(frappe.ValidationError):
            self._save("http://fcm.googleapis.com/fcm/send/x")

    def test_real_fcm_endpoint_passes_the_gate(self):
        """Non-vacuity control: the refusals above are the allowlist, not the mocks."""
        doc = MagicMock()
        with patch.object(
            portal_notifications.frappe.db, "get_value", return_value=None
        ), patch.object(portal_notifications.frappe, "new_doc", return_value=doc) as new_doc:
            res = self._save(_REAL_FCM)
        new_doc.assert_called_once()
        doc.save.assert_called_once_with(ignore_permissions=True)
        self.assertTrue(res["subscribed"])
