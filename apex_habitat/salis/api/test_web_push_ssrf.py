"""SSRF allowlist tests for the driver Web Push endpoint.

The browser-supplied PushSubscription ``endpoint`` becomes a server-side POST target
in ``web_push._deliver``, so it is an SSRF sink. These tests prove the allowlist gate:
``is_allowed_push_endpoint`` admits only https:// URLs on a known push provider and
refuses internal/loopback/link-local/metadata hosts and non-https schemes; the
save-time gate in ``save_push_subscription`` rejects a hostile endpoint before it is
ever stored. No real network call is made — delivery is never invoked here.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from apex_habitat.salis.api import driver_portal, web_push

_REAL_FCM = "https://fcm.googleapis.com/fcm/send/abc123:DEF456"
_REAL_APPLE = "https://web.push.apple.com/QABCDEF/notification"
_REAL_WNS = "https://db5.notify.windows.com/w/?token=AaBb"
_REAL_MOZILLA = "https://updates.push.services.mozilla.com/wpush/v2/gAAAA"

# Endpoints that must never be stored or POSTed to (internal / non-provider / non-https).
_HOSTILE = [
    "http://localhost/push",  # loopback name, non-https
    "https://localhost/push",  # loopback name
    "http://127.0.0.1/push",  # loopback IP
    "https://127.0.0.1/push",  # loopback IP, https
    "http://169.254.169.254/latest/meta-data/",  # cloud metadata (link-local)
    "https://169.254.169.254/latest/meta-data/",  # metadata over https
    "https://10.0.0.5/push",  # RFC-1918 private
    "https://192.168.1.10/push",  # RFC-1918 private
    "https://172.16.0.9/push",  # RFC-1918 private
    "https://[::1]/push",  # IPv6 loopback
    "http://fcm.googleapis.com/fcm/send/x",  # right host, wrong (non-https) scheme
    "https://fcm.googleapis.com.evil.com/x",  # exact-host spoof via suffix
    "https://evil-push.apple.com/x",  # suffix spoof, no dot boundary
    "https://evil.com/x",  # arbitrary external host
    "ftp://fcm.googleapis.com/x",  # non-http(s) scheme
    "",  # empty
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


class TestSavePushSubscriptionGate(FrappeTestCase):
    """``save_push_subscription`` rejects a hostile endpoint before any persistence."""

    def setUp(self):
        # Neutralise identity/config gates so only the SSRF check is under test; no DB.
        self._patches = [
            patch.object(driver_portal, "_require_enabled", return_value=None),
            patch.object(driver_portal, "_resolve_driver", return_value="DRV-0001"),
            patch.object(web_push, "is_configured", return_value=True),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()

    def test_internal_host_endpoint_is_rejected_at_save(self):
        # An internal/metadata host must throw and never reach the DocType layer.
        for ep in ("http://localhost/push", "http://169.254.169.254/latest/meta-data/"):
            with patch.object(driver_portal.frappe, "get_doc") as get_doc, patch.object(
                driver_portal.frappe, "new_doc"
            ) as new_doc:
                with self.assertRaises(frappe.ValidationError):
                    driver_portal.save_push_subscription(endpoint=ep)
                get_doc.assert_not_called()
                new_doc.assert_not_called()

    def test_non_https_endpoint_is_rejected_at_save(self):
        with self.assertRaises(frappe.ValidationError):
            driver_portal.save_push_subscription(endpoint="http://fcm.googleapis.com/fcm/send/x")

    def test_real_fcm_endpoint_passes_the_gate(self):
        # A genuine FCM endpoint clears the SSRF gate and reaches persistence (mocked,
        # so no real row/network). Proves the gate does not block valid push.
        doc = MagicMock(name="DRV-PUSH-NEW")
        doc.name = "DRV-PUSH-NEW"
        with patch.object(
            driver_portal.frappe.db, "get_value", return_value=None
        ), patch.object(driver_portal.frappe, "new_doc", return_value=doc) as new_doc:
            res = driver_portal.save_push_subscription(
                endpoint=_REAL_FCM, p256dh="key", auth="secret", user_agent="ua"
            )
        new_doc.assert_called_once()  # gate passed -> we built the subscription doc
        doc.save.assert_called_once()
        self.assertEqual(res["name"], "DRV-PUSH-NEW")
