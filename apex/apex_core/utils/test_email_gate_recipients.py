# Copyright (c) 2026, afmcoltd
"""A-366 — the recipient filter must honour the person's own email choice.

Every explicit ``frappe.sendmail`` site in the app guarded on the Habitat Settings
kill-switch, which answers whether the APP may send. None of them asked whether the PERSON
agreed to receive, and the two are different questions:

* ``frappe.sendmail`` itself honours neither. Only four callers inside frappe consult
  ``is_email_notifications_enabled`` — Communication, Notification Log, Event and Energy
  Point Log — so a raw send bypasses the setting entirely.
* ``User.enabled`` is the LOGIN flag. A user who can log in perfectly well and has switched
  their own email notifications off still passes it, which is exactly the shape the digests
  were filtering on.

These tests run against a real site because the claim under test is about stored
Notification Settings rows, not about call shape.

Nothing here builds a User. ``test_dependencies = ["User"]`` stands frappe's own three
unprivileged fixture users up once per run, and each case that needs an unwilling or
disabled recipient BORROWS one and hands it back — the previous form of this file minted
three Users and deleted them again in class cleanup.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.apex_core.utils.email_gate import mailable

test_dependencies = ["User"]

WILLING = "test1@example.com"
OPTED_OUT = "test2@example.com"
DISABLED = "test3@example.com"


class TestMailableHonoursTheUsersOwnChoice(FrappeTestCase):
    def setUp(self):
        # Both of these are shared fixture rows, so what this class switches off it
        # switches back on. A fixture is only reusable while every test leaves it as it
        # found it.
        self.addCleanup(self._set_email_notifications, OPTED_OUT, 1)
        self.addCleanup(frappe.db.set_value, "User", DISABLED, "enabled", 1)

        self._set_email_notifications(OPTED_OUT, 0)
        frappe.db.set_value("User", DISABLED, "enabled", 0)

    @staticmethod
    def _set_email_notifications(user, value):
        settings = frappe.get_doc("Notification Settings", user)
        settings.enable_email_notifications = value
        settings.save(ignore_permissions=True)

    def test_a_user_who_switched_email_off_is_dropped(self):
        """The defect this card names: they are enabled, they can log in, and they said
        no."""
        self.assertEqual(mailable([OPTED_OUT]), [])

    def test_the_login_flag_alone_would_have_kept_them(self):
        """Proves the old filter was the wrong question, not merely a weaker one."""
        self.assertTrue(frappe.db.get_value("User", OPTED_OUT, "enabled"))

    def test_a_willing_user_still_receives(self):
        """A filter that drops everyone would pass the test above and ship silence."""
        self.assertEqual(mailable([WILLING]), [WILLING])

    def test_a_disabled_login_is_still_dropped(self):
        self.assertEqual(mailable([DISABLED]), [])

    def test_administrator_and_guest_are_never_recipients(self):
        self.assertEqual(mailable(["Administrator", "Guest"]), [])

    def test_order_is_preserved_and_only_the_unwilling_are_removed(self):
        self.assertEqual(
            mailable([WILLING, OPTED_OUT, DISABLED, WILLING]),
            [WILLING, WILLING],
        )

    def test_empty_and_falsy_input_is_safe(self):
        self.assertEqual(mailable([]), [])
        self.assertEqual(mailable(None), [])
        self.assertEqual(mailable(["", None]), [])
