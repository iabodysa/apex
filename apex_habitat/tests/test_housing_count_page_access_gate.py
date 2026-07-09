# Copyright (c) 2026, AFMCO and contributors
"""Access gate of the unified /housing portal (count + delivery flows).

The housing portal is an admin-style surface, not a guest link, so its gate must
hold (mirrors test_safety_page_access_gate):
  * a Guest is redirected to /login (then back to /housing);
  * a logged-in user WITHOUT a housing role gets the friendly no-role page —
    has_housing_role is False and NO CSRF token is issued to them;
  * a housing-role user gets has_housing_role True + a CSRF token for the
    whitelisted submit_counts / pass_exit_* / confirm_receipt POSTs.

The count portal moved from /housing-count to /housing (the SPA now serves both
the Housing Inventory count and the Facility Asset Delivery clearance), so the
gate that used to live on www/housing_count.py now lives on www/housing.py and
these assertions are re-homed onto it. The import below is a regression guard:
Frappe maps a route template to an UNDERSCORED python module, and www/housing.py
is already underscored, so it is always imported and get_context always runs.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex_habitat.www import housing


class TestHousingPageAccessGate(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")

    def tearDown(self):
        frappe.set_user("Administrator")

    def _user_with_roles(self, email, roles):
        if not frappe.db.exists("User", email):
            frappe.get_doc(
                {
                    "doctype": "User",
                    "email": email,
                    "first_name": email.split("@")[0],
                    "roles": [{"role": r} for r in roles],
                }
            ).insert(ignore_permissions=True)
        return email

    def test_guest_is_redirected_to_login(self):
        frappe.set_user("Guest")
        try:
            with self.assertRaises(frappe.Redirect):
                housing.get_context(frappe._dict())
            self.assertEqual(
                frappe.local.flags.redirect_location,
                "/login?redirect-to=/housing",
                "a Guest must be sent to login and back to /housing",
            )
        finally:
            frappe.set_user("Administrator")

    def test_non_housing_role_gets_friendly_no_role_page(self):
        frappe.set_user(self._user_with_roles("housing-gate-norole@test.local", ["Internal Auditor"]))
        try:
            ctx = housing.get_context(frappe._dict())
            self.assertFalse(ctx.has_housing_role, "a non-housing user must not pass the gate")
            self.assertIsNone(ctx.get("csrf_token"), "no CSRF token may be issued to a non-housing user")
        finally:
            frappe.set_user("Administrator")

    def test_housing_role_gets_access_and_csrf(self):
        frappe.set_user(self._user_with_roles("housing-gate-mgr@test.local", ["Accommodation Manager"]))
        try:
            ctx = housing.get_context(frappe._dict())
            self.assertTrue(ctx.has_housing_role, "an Accommodation Manager must pass the gate")
            self.assertTrue(ctx.get("csrf_token"), "a housing user must receive a CSRF token")
        finally:
            frappe.set_user("Administrator")

    def test_system_manager_passes(self):
        ctx = housing.get_context(frappe._dict())
        self.assertTrue(ctx.has_housing_role, "a System Manager must pass the housing gate")
