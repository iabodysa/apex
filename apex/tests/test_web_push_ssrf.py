# Copyright (c) 2026, AFMCO and contributors
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

from apex.salis.api import driver_portal, web_push

_REAL_FCM = "https://fcm.googleapis.com/fcm/send/abc123:DEF456"
_REAL_APPLE = "https://web.push.apple.com/QABCDEF/notification"
_REAL_WNS = "https://db5.notify.windows.com/w/?token=AaBb"
_REAL_MOZILLA = "https://updates.push.services.mozilla.com/wpush/v2/gAAAA"

# [#hb8rda]
_HOSTILE = [
    "http://localhost/push",  # [#mslqpm]
    "https://localhost/push",  # [#nn5er2]
    "http://127.0.0.1/push",  # [#87n9dc]
    "https://127.0.0.1/push",  # [#onegft]
    "http://169.254.169.254/latest/meta-data/",  # [#1ll2x5]
    "https://169.254.169.254/latest/meta-data/",  # [#zjyg10]
    "https://10.0.0.5/push",  # [#lktwqn]
    "https://192.168.1.10/push",  # [#lktwqn]
    "https://172.16.0.9/push",  # [#lktwqn]
    "https://[::1]/push",  # [#elgdeb]
    "http://fcm.googleapis.com/fcm/send/x",  # [#asn96m]
    "https://fcm.googleapis.com.evil.com/x",  # [#k6bm6k]
    "https://evil-push.apple.com/x",  # [#6yq4k8]
    "https://evil.com/x",  # [#9ewpnn]
    "ftp://fcm.googleapis.com/x",  # [#tvauq1]
    "",  # [#qmta63]
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
        # [#q9nvck]
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
        # [#kx0zh9]
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
        # [#ihwtf4]
        doc = MagicMock(name="DRV-PUSH-NEW")
        doc.name = "DRV-PUSH-NEW"
        with patch.object(
            driver_portal.frappe.db, "get_value", return_value=None
        ), patch.object(driver_portal.frappe, "new_doc", return_value=doc) as new_doc:
            res = driver_portal.save_push_subscription(
                endpoint=_REAL_FCM, p256dh="key", auth="secret", user_agent="ua"
            )
        new_doc.assert_called_once()  # [#754ove]
        doc.save.assert_called_once()
        self.assertEqual(res["name"], "DRV-PUSH-NEW")
