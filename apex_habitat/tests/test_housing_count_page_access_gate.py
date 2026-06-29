# Copyright (c) 2026, AFMCO and contributors
"""Access gate of the /housing-count Housing Inventory count portal.

The count portal is an admin-style surface, not a guest link, so its gate must
hold (mirrors test_safety_page_access_gate):
  * a Guest is redirected to /login (then back to /housing-count);
  * a logged-in user WITHOUT a count role gets the friendly no-role page —
    has_count_role is False and NO CSRF token is issued to them;
  * a count-role user gets has_count_role True + a CSRF token for submit_counts.

The controller MUST live at www/housing_count.py (underscored), not the
hyphenated www/housing-count.py: Frappe's TemplatePage maps the hyphenated route
template to an UNDERSCORED python module (template_basepath.replace("-", "_")), so
a hyphenated controller is silently never imported and get_context never runs —
the page then renders the no-role else-branch for EVERYONE (even a System
Manager). The import below is the regression guard for that.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex_habitat.www import housing_count


class TestHousingCountPageAccessGate(FrappeTestCase):
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
                housing_count.get_context(frappe._dict())
            self.assertEqual(
                frappe.local.flags.redirect_location,
                "/login?redirect-to=/housing-count",
                "a Guest must be sent to login and back to /housing-count",
            )
        finally:
            frappe.set_user("Administrator")

    def test_non_count_role_gets_friendly_no_role_page(self):
        frappe.set_user(self._user_with_roles("count-gate-norole@test.local", ["Internal Auditor"]))
        try:
            ctx = housing_count.get_context(frappe._dict())
            self.assertFalse(ctx.has_count_role, "a non-count user must not pass the gate")
            self.assertIsNone(ctx.get("csrf_token"), "no CSRF token may be issued to a non-count user")
        finally:
            frappe.set_user("Administrator")

    def test_count_role_gets_access_and_csrf(self):
        frappe.set_user(self._user_with_roles("count-gate-mgr@test.local", ["Accommodation Manager"]))
        try:
            ctx = housing_count.get_context(frappe._dict())
            self.assertTrue(ctx.has_count_role, "an Accommodation Manager must pass the gate")
            self.assertTrue(ctx.get("csrf_token"), "a count user must receive a CSRF token")
        finally:
            frappe.set_user("Administrator")

    def test_system_manager_passes(self):
        # The bug this guards: a hyphenated controller never loads, so even a
        # System Manager (Administrator's tier) saw the no-role page.
        ctx = housing_count.get_context(frappe._dict())
        self.assertTrue(ctx.has_count_role, "a System Manager must pass the count gate")
