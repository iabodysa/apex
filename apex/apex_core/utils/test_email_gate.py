# Copyright (c) 2026, afmcoltd

"""``mailable`` gates a Frappe User's own consent — the login flag and their
Notification Settings opt-out. A configured external address
(``Habitat Settings.finance_notification_email``, ``safety_report_recipient``)
has neither: it names no User row at all, so it must pass through rather than
read as a disabled login.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.apex_core.utils.email_gate import mailable

EXTERNAL_ADDRESS = "no-such-user-on-this-site@example.com"


class TestMailableKeepsAnAddressWithNoUserRow(FrappeTestCase):
    def setUp(self):
        self.assertIsNone(frappe.db.exists("User", EXTERNAL_ADDRESS))

    def test_an_address_with_no_user_row_passes_through(self):
        self.assertEqual(mailable([EXTERNAL_ADDRESS]), [EXTERNAL_ADDRESS])

    def test_administrator_and_guest_are_still_dropped(self):
        self.assertEqual(mailable(["Administrator", "Guest", EXTERNAL_ADDRESS]), [EXTERNAL_ADDRESS])

    def test_a_disabled_real_user_is_still_dropped(self):
        user = "apex-test-mailable-disabled@example.com"
        if not frappe.db.exists("User", user):
            frappe.get_doc(
                {"doctype": "User", "email": user, "first_name": "Apex Test", "enabled": 0}
            ).insert(ignore_permissions=True)
        else:
            frappe.db.set_value("User", user, "enabled", 0)

        self.assertEqual(mailable([user, EXTERNAL_ADDRESS]), [EXTERNAL_ADDRESS])
