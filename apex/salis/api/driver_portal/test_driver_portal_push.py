# Copyright (c) 2026, AFMCO and contributors
"""Driver Web Push scaffold: the opt-in endpoints + the no-op-until-VAPID contract.

Web Push delivery needs a VAPID key pair the operator provisions; until then every
send must be a safe no-op and the SPA must see push as unconfigured. These tests pin
that contract WITHOUT any keys on file (the shipped state):

  * ``web_push.send_to_driver`` / ``enqueue_to_driver`` no-op (reason ``not_configured``)
    when the toggle is off, never raising and never enqueuing;
  * ``get_push_config`` reports ``enabled: False`` so the SPA hides the opt-in;
  * ``save_push_subscription`` refuses (the client cannot bank a subscription a portal
    can never deliver to);
  * with the toggle + a VAPID pair set, the opt-in stores a Driver Push Subscription
    scoped to the resolved driver, a re-subscribe updates in place (unique endpoint),
    opt-out disables it, and a send still no-ops cleanly because ``pywebpush`` is not
    installed (the integration seam) rather than erroring.

The driver chain reuses the shared ``_ensure_test_driver`` builder; everything lives in
the class transaction and rolls back at teardown.

``TestVapidKeyPairGuard`` at the foot of the file covers the one state the class above
cannot reach: the toggle ON with only HALF a key pair. Every case above blanks the keys
and the toggle together, so the master-toggle guard returns first and the pair check
below it never runs.
"""

import unittest
from unittest import mock

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.salis.api import driver_portal, web_push
from apex.tests.factories import make_test_driver as _ensure_test_driver

_VAPID_FIELDS = (
    "enable_web_push",
    "web_push_vapid_public_key",
    "web_push_vapid_private_key",
    "web_push_vapid_subject",
)
# [#q83lgd]
_TEST_PUBLIC = "BNtest_public_key_value_for_unit_tests_only_000000000000000000000000000000000000000000"
_TEST_PRIVATE = "test_private_key_value_for_unit_tests_only"


class TestDriverPortalWebPush(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        frappe.db.set_single_value("Salis Settings", "enable_driver_portal", 1)
        cls.driver = _ensure_test_driver()
        cls.user = frappe.db.get_value(
            "Employee", frappe.db.get_value("Salis Driver", cls.driver, "employee"), "user_id"
        )

    def setUp(self):
        # [#89umw4]
        frappe.set_user("Administrator")
        self._set_push(enabled=0, public="", private="")
        self._clear_subscriptions()

    def tearDown(self):
        frappe.set_user("Administrator")
        self._set_push(enabled=0, public="", private="")
        self._clear_subscriptions()

    def _clear_subscriptions(self):
        frappe.db.delete("Driver Push Subscription", {"driver": self.driver})

    def _set_push(self, enabled, public, private, subject="mailto:test@example.com"):
        frappe.db.set_single_value(
            "Salis Settings",
            {
                "enable_web_push": enabled,
                "web_push_vapid_public_key": public,
                "web_push_vapid_private_key": private,
                "web_push_vapid_subject": subject,
            },
        )

    def _configure_push(self):
        self._set_push(enabled=1, public=_TEST_PUBLIC, private=_TEST_PRIVATE)

    # [#mnfove]

    def test_send_noop_when_unconfigured(self):
        """With push off, a send is a logged no-op (never raises) and reports why."""
        r = web_push.send_to_driver(self.driver, "T", "Body")
        self.assertEqual(r["sent"], 0)
        self.assertEqual(r["reason"], "not_configured")

    def test_enqueue_noop_when_unconfigured(self):
        """An unconfigured enqueue does not even wake the worker."""
        r = web_push.enqueue_to_driver(self.driver, "T", "Body")
        self.assertFalse(r["queued"])
        self.assertEqual(r["reason"], "not_configured")

    def test_is_configured_false_when_the_toggle_is_off(self):
        """The shipped state: toggle off AND no keys, so the MASTER TOGGLE guard
		(web_push.py:80) is what returns and the pair check below it never runs. Named
		for the toggle, not the keys -- ``TestVapidKeyPairGuard`` covers the pair.
		"""
        self.assertFalse(web_push.is_configured())
        self.assertIsNone(web_push.public_key())

    def test_get_push_config_disabled_for_driver(self):
        """The SPA bootstrap reports push off, so the opt-in stays hidden."""
        frappe.set_user(self.user)
        cfg = driver_portal.get_push_config()
        frappe.set_user("Administrator")
        self.assertFalse(cfg["enabled"])
        self.assertFalse(cfg["subscribed"])

    def test_save_subscription_refused_when_unconfigured(self):
        """A driver cannot bank a subscription against a portal that can never deliver."""
        frappe.set_user(self.user)
        with self.assertRaises(frappe.PermissionError):
            driver_portal.save_push_subscription(endpoint="https://push.example/abc")
        frappe.set_user("Administrator")

    # [#q1ukeh]

    def test_config_exposes_public_key_only(self):
        """Configured, is_configured is true and only the PUBLIC key is exposed."""
        self._configure_push()
        self.assertTrue(web_push.is_configured())
        self.assertEqual(web_push.public_key(), _TEST_PUBLIC)
        frappe.set_user(self.user)
        cfg = driver_portal.get_push_config()
        frappe.set_user("Administrator")
        self.assertTrue(cfg["enabled"])
        self.assertEqual(cfg["vapid_public_key"], _TEST_PUBLIC)
        self.assertNotIn("web_push_vapid_private_key", cfg)
        self.assertNotIn("vapid_private_key", cfg)

    def test_opt_in_stores_scoped_subscription(self):
        """Opt-in creates one Driver Push Subscription bound to the resolved driver."""
        self._configure_push()
        endpoint = "https://fcm.googleapis.com/fcm/send/endpoint-1"
        frappe.set_user(self.user)
        res = driver_portal.save_push_subscription(
            endpoint=endpoint, p256dh="pkey", auth="asecret", user_agent="UA/1.0"
        )
        frappe.set_user("Administrator")
        self.assertTrue(res["name"])
        row = frappe.db.get_value(
            "Driver Push Subscription", res["name"], ["driver", "user", "enabled"], as_dict=True
        )
        self.assertEqual(row.driver, self.driver)
        self.assertEqual(row.user, self.user)
        self.assertTrue(row.enabled)
        # [#tn43gl]
        self.assertEqual(
            frappe.db.get_value("Driver Push Subscription", {"endpoint": endpoint}, "driver"),
            self.driver,
        )

    def test_resubscribe_updates_in_place(self):
        """A re-subscribe on the same endpoint updates the row, never duplicates."""
        self._configure_push()
        endpoint = "https://fcm.googleapis.com/fcm/send/endpoint-2"
        frappe.set_user(self.user)
        first = driver_portal.save_push_subscription(endpoint=endpoint, p256dh="k1", auth="a1")
        second = driver_portal.save_push_subscription(endpoint=endpoint, p256dh="k2", auth="a2")
        frappe.set_user("Administrator")
        self.assertEqual(first["name"], second["name"])
        self.assertEqual(
            frappe.db.count("Driver Push Subscription", {"endpoint": endpoint}), 1
        )

    def test_opt_out_disables_subscription(self):
        """Opt-out disables (audit-keeps) the driver's own device only."""
        self._configure_push()
        endpoint = "https://fcm.googleapis.com/fcm/send/endpoint-3"
        frappe.set_user(self.user)
        driver_portal.save_push_subscription(endpoint=endpoint, p256dh="k", auth="a")
        out = driver_portal.delete_push_subscription(endpoint=endpoint)
        frappe.set_user("Administrator")
        self.assertTrue(out["disabled"])
        self.assertEqual(
            frappe.db.get_value("Driver Push Subscription", {"endpoint": endpoint}, "enabled"), 0
        )

    def test_send_noops_without_pywebpush_even_when_configured(self):
        """Configured + an opted-in device, the send still no-ops cleanly because the
		delivery library is not bundled — the integration seam, never an error."""
        self._configure_push()
        frappe.set_user(self.user)
        driver_portal.save_push_subscription(
            endpoint="https://fcm.googleapis.com/fcm/send/endpoint-4", p256dh="k", auth="a"
        )
        frappe.set_user("Administrator")
        # [#cn3oba]
        r = web_push.send_to_driver(self.driver, "Trip assigned", "Your next trip is ready.")
        self.assertEqual(r["sent"], 0)
        self.assertEqual(r["devices"], 1)


class _FakeSettings:
    """Only the two reads ``_vapid_config`` makes off the Single."""

    def __init__(self, values, private):
        self._values = values
        self._private = private

    def get(self, field, *args):
        return self._values.get(field)

    def get_password(self, field, raise_exception=True):
        return self._private


class TestVapidKeyPairGuard(unittest.TestCase):
    """The toggle ON with only HALF a VAPID pair -- a state nothing else reaches.

	``test_is_configured_false_when_the_toggle_is_off`` and every sibling blank the keys
	and the toggle TOGETHER, so the master-toggle guard (web_push.py:80) returns first
	and the pair check below it (web_push.py:85) is exercised by nothing: deleting that
	check outright would leave the whole file green. The state it exists for is an
	operator who enables push having pasted only the public key -- without it, a send
	would go out to sign with a private key that is None.

	The Single is stubbed rather than written, so this needs no site and no settings
	row: a credential guard that can only be exercised against a live bench is a guard
	that does not get tested.
	"""

    def _config_with(self, public, private):
        settings = _FakeSettings(
            {
                "enable_web_push": 1,
                "web_push_vapid_public_key": public,
                "web_push_vapid_subject": "mailto:ops@example.com",
            },
            private,
        )
        with mock.patch.object(web_push.frappe, "get_single", return_value=settings):
            return web_push._vapid_config()

    def test_the_toggle_on_with_half_a_pair_is_still_unconfigured(self):
        for label, public, private in (
            ("private unset", _TEST_PUBLIC, None),
            ("private blank", _TEST_PUBLIC, ""),
            ("public blank", "", _TEST_PRIVATE),
            ("public whitespace only", "   ", _TEST_PRIVATE),
        ):
            with self.subTest(case=label):
                self.assertIsNone(
                    self._config_with(public, private),
                    "push reported itself configured on half a key pair, so a send "
                    "would sign with a missing key",
                )

    def test_the_toggle_on_with_a_whole_pair_is_configured(self):
        """Non-vacuous: the guard must decline a HALF pair, not every enabled config.

		Without this, replacing the body with ``return None`` would pass the test above
		and retire web push entirely while the suite stayed green.
		"""
        config = self._config_with(_TEST_PUBLIC, _TEST_PRIVATE)

        self.assertEqual(config["public_key"], _TEST_PUBLIC)
        self.assertEqual(config["private_key"], _TEST_PRIVATE)
