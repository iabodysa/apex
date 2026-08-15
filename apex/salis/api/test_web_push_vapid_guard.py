# Copyright (c) 2026, AFMCO and contributors
"""Web Push reads its VAPID pair off a Single, and everything downstream depends on it.

``_vapid_config`` is the one place that decides whether push is usable. Two states have
to hold or a portal either signs with a missing key or raises at a driver:

  * the shipped state — the master toggle off — makes every send and every enqueue a
    reported no-op rather than an exception, and hides the opt-in from the SPA;
  * the toggle ON with only HALF a key pair. Nothing else reaches it: every other case
    blanks the toggle and the keys together, so the toggle guard returns first and the
    pair check below it is exercised by nothing — deleting that check outright would
    leave the rest green. It exists for an operator who pasted only the public key.

The Single is stubbed rather than written, so this needs no settings row: a credential
guard that can only be exercised against a live bench is a guard that does not get run.
"""

import unittest
from unittest import mock

from apex.apex_core.utils.portal_identity import DRIVER
from apex.salis.api import web_push

_TEST_PUBLIC = "BNtest_public_key_value_for_unit_tests_only_00000000000000000000000000000000000"
_TEST_PRIVATE = "test_private_key_value_for_unit_tests_only"


class _FakeSettings:
    """Only the two reads ``_vapid_config`` makes off the Single."""

    def __init__(self, values, private):
        self._values = values
        self._private = private

    def get(self, field, *args):
        return self._values.get(field)

    def get_password(self, field, raise_exception=True):
        return self._private


def _settings(enabled, public, private):
    return _FakeSettings(
        {
            "enable_web_push": enabled,
            "web_push_vapid_public_key": public,
            "web_push_vapid_subject": "mailto:ops@example.com",
        },
        private,
    )


class TestVapidConfigGuard(unittest.TestCase):
    def _config_with(self, enabled, public, private):
        with mock.patch.object(
            web_push.frappe, "get_single", return_value=_settings(enabled, public, private)
        ):
            return web_push._vapid_config()

    def test_a_complete_pair_with_the_toggle_on_is_configured(self):
        """Non-vacuity control: the refusals below are the guard, not the stub."""
        config = self._config_with(1, _TEST_PUBLIC, _TEST_PRIVATE)
        self.assertIsNotNone(config)
        self.assertEqual(config["public_key"], _TEST_PUBLIC)

    def test_the_toggle_off_is_unconfigured_whatever_the_keys_say(self):
        self.assertIsNone(self._config_with(0, _TEST_PUBLIC, _TEST_PRIVATE))

    def test_the_toggle_on_with_half_a_pair_is_still_unconfigured(self):
        for label, public, private in (
            ("private unset", _TEST_PUBLIC, None),
            ("private blank", _TEST_PUBLIC, ""),
            ("public blank", "", _TEST_PRIVATE),
            ("public whitespace only", "   ", _TEST_PRIVATE),
        ):
            with self.subTest(case=label):
                self.assertIsNone(
                    self._config_with(1, public, private),
                    "push reported itself configured on half a key pair, so a send "
                    "would sign with a missing key",
                )


class TestUnconfiguredPushIsAReportedNoOp(unittest.TestCase):
    """With no usable pair nothing raises, nothing is queued, and the reason is named."""

    def setUp(self):
        patcher = mock.patch.object(
            web_push.frappe, "get_single", return_value=_settings(0, "", "")
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_is_configured_and_public_key_report_the_absence(self):
        self.assertFalse(web_push.is_configured())
        self.assertIsNone(web_push.public_key())

    def test_a_send_is_a_no_op_that_names_its_reason(self):
        result = web_push.send_to_driver("DRV-0001", "Trip assigned", "Your next trip is ready.")
        self.assertEqual(result, {"sent": 0, "reason": "not_configured"})

    def test_an_enqueue_does_not_even_wake_the_worker(self):
        with mock.patch.object(web_push.frappe, "enqueue") as enqueue:
            result = web_push.enqueue_to_subject(DRIVER, "DRV-0001", "Trip assigned", "Body")
        enqueue.assert_not_called()
        self.assertEqual(result, {"queued": False, "reason": "not_configured"})
