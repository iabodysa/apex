# Copyright (c) 2026, AFMCO and contributors
"""Access gate of the /safety Safety Rounds portal (www/safety.py get_context).

The Safety Checklist portal is an admin-style surface, not a guest link, so its
gate must hold (mirrors test_fleet_page_access_gate):
  * a Guest is redirected to /login (then back to /safety);
  * a logged-in user WITHOUT a safety role gets the friendly no-role page —
    has_safety_role is False and NO CSRF token is issued to them;
  * only a safety-role user (the submit-capable roles) gets has_safety_role True
    + a CSRF token for the portal's submit_due_rounds POST.

A regression that issued the token (or has_safety_role) to a non-safety user
would expose the safety portal, and a broken guest branch would either 403 or
leak the portal to anonymous traffic. Safety Officer is intentionally NOT a
safety-portal role (it cannot submit a Safety Round), so it must be refused too.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex_habitat.www import safety


class TestSafetyPageAccessGate(FrappeTestCase):
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
                safety.get_context(frappe._dict())
            self.assertEqual(
                frappe.local.flags.redirect_location,
                "/login?redirect-to=/safety",
                "a Guest must be sent to login and back to /safety",
            )
        finally:
            frappe.set_user("Administrator")

    def test_non_safety_role_gets_friendly_no_role_page(self):
        # A real, non-safety role: the gate must close (no redirect, no token).
        frappe.set_user(self._user_with_roles("safety-gate-norole@test.local", ["Internal Auditor"]))
        try:
            ctx = safety.get_context(frappe._dict())
            self.assertFalse(ctx.has_safety_role, "a non-safety user must not pass the gate")
            self.assertIsNone(ctx.get("csrf_token"), "no CSRF token may be issued to a non-safety user")
        finally:
            frappe.set_user("Administrator")

    def test_safety_officer_is_refused(self):
        # Safety Officer can record but NOT submit a round, so the portal (which
        # submits) must refuse it — guards the role list against drift.
        frappe.set_user(self._user_with_roles("safety-gate-officer@test.local", ["Safety Officer"]))
        try:
            ctx = safety.get_context(frappe._dict())
            self.assertFalse(ctx.has_safety_role, "Safety Officer cannot submit and must be refused")
            self.assertIsNone(ctx.get("csrf_token"))
        finally:
            frappe.set_user("Administrator")

    def test_safety_role_gets_access_and_csrf(self):
        frappe.set_user(self._user_with_roles("safety-gate-mgr@test.local", ["Accommodation Manager"]))
        try:
            ctx = safety.get_context(frappe._dict())
            self.assertTrue(ctx.has_safety_role, "an Accommodation Manager must pass the gate")
            self.assertTrue(ctx.get("csrf_token"), "a safety user must receive a CSRF token")
        finally:
            frappe.set_user("Administrator")
