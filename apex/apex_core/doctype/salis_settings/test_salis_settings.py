# Copyright (c) 2026, afmcoltd
"""What Salis Settings guarantees, asserted against the DocType itself.

Patterned on frappe's own document-validation tests (``frappe/tests/test_document.py``,
``test_validate``). This is a Single — one standing row shared by the whole suite — so
every case that changes a value restores it with ``self.addCleanup`` before returning.

Two guarantees pinned here: the employee advance recovery percent is bounded to
``(0, MAX_RECOVERY_PERCENT]``, and a Web Push VAPID public key — when web push is
enabled — must decode to the exact 65-byte, ``0x04``-prefixed uncompressed P-256 point
``PushManager.subscribe`` requires, or the refusal never reaches the person who pasted a
truncated or re-encoded key, only the driver whose subscribe call fails in the browser.
"""

import base64

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.apex_core.setup.employee_advance_recovery import MAX_RECOVERY_PERCENT


def _valid_vapid_key() -> str:
    """A syntactically valid (not cryptographically real) uncompressed P-256 point:
    65 bytes starting with 0x04, base64url-encoded with no padding, the shape the
    browser's PushManager actually hands back."""
    point = bytes([4]) + bytes(64)
    return base64.urlsafe_b64encode(point).decode().rstrip("=")


class TestSalisSettings(FrappeTestCase):
    def setUp(self):
        self._original = frappe.db.get_singles_dict("Salis Settings")
        self.addCleanup(self._restore_settings)

    def _restore_settings(self):
        for field, value in self._original.items():
            frappe.db.set_single_value("Salis Settings", field, value)

    def test_an_advance_recovery_percent_above_the_maximum_is_refused(self):
        """A percent above the policy ceiling would recover more of a worker's salary
        than the deployment allows, so it is refused at the settings level rather than
        capped silently on every payroll run."""
        settings = frappe.get_single("Salis Settings")
        settings.employee_advance_recovery_max_percent = MAX_RECOVERY_PERCENT + 1

        with self.assertRaisesRegex(
            frappe.ValidationError, "must be greater than 0"
        ):
            settings.save()

    def test_an_advance_recovery_percent_at_the_maximum_is_accepted(self):
        """The acceptance counterpart — the ceiling itself is inclusive, so the boundary
        value must still save."""
        settings = frappe.get_single("Salis Settings")
        settings.employee_advance_recovery_max_percent = MAX_RECOVERY_PERCENT
        settings.save()

        self.assertEqual(
            frappe.db.get_single_value(
                "Salis Settings", "employee_advance_recovery_max_percent"
            ),
            MAX_RECOVERY_PERCENT,
        )

    def test_enabling_web_push_without_a_key_is_refused(self):
        """Web push cannot be turned on with nothing for the browser to subscribe
        against."""
        settings = frappe.get_single("Salis Settings")
        settings.enable_web_push = 1
        settings.web_push_vapid_public_key = ""

        with self.assertRaisesRegex(
            frappe.ValidationError, "VAPID public key is required"
        ):
            settings.save()

    def test_enabling_web_push_with_a_wrong_length_key_is_refused(self):
        """A key that does not decode to exactly 65 bytes is rejected here rather than
        by the browser's ``PushManager.subscribe`` at the worker's device, where nobody
        can act on the error."""
        settings = frappe.get_single("Salis Settings")
        settings.enable_web_push = 1
        settings.web_push_vapid_public_key = base64.urlsafe_b64encode(
            bytes(10)
        ).decode().rstrip("=")

        with self.assertRaisesRegex(
            frappe.ValidationError, "must decode to 65 bytes"
        ):
            settings.save()

    def test_enabling_web_push_with_a_valid_key_is_accepted(self):
        """The acceptance counterpart — a correctly shaped 65-byte, 0x04-prefixed key
        must still let web push turn on."""
        settings = frappe.get_single("Salis Settings")
        settings.enable_web_push = 1
        settings.web_push_vapid_public_key = _valid_vapid_key()
        settings.save()

        self.assertEqual(
            frappe.db.get_single_value("Salis Settings", "enable_web_push"), 1
        )
