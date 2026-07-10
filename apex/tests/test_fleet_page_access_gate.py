# Copyright (c) 2026, AFMCO and contributors
"""Access gate of the /fleet supervisor dashboard (www/fleet.py get_context).

The fleet board is an ADMIN surface, not a guest portal, so its gate must hold:
  * a Guest is redirected to /login (then back to /fleet);
  * a logged-in user WITHOUT a fleet role gets the friendly no-role page —
    has_fleet_role is False and NO CSRF token is issued to them;
  * only a fleet-role user gets has_fleet_role True + a CSRF token for the
    board's whitelisted POSTs (reassign / stop / theft / workshop / recover).

No test covered this gate. A regression that issued the token (or has_fleet_role)
to a non-fleet user would expose the live fleet board, and a broken guest branch
would either 403 or leak the board to anonymous traffic. This is the "page"
half of T-219 (the workspace/cards/charts/onboarding structure is guarded by
test_schema_integrity + test_workspace_content_blocks_resolve + the number-card
and onboarding guards; the "non-zero with real data" half needs the production
import and stays owner-gated).
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.www import fleet


class TestFleetPageAccessGate(FrappeTestCase):
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
                fleet.get_context(frappe._dict())
            self.assertEqual(
                frappe.local.flags.redirect_location,
                "/login?redirect-to=/fleet",
                "a Guest must be sent to login and back to /fleet",
            )
        finally:
            frappe.set_user("Administrator")

    def test_non_fleet_role_gets_friendly_no_role_page(self):
        # A real, non-fleet role: the gate must close (no redirect, no token).
        frappe.set_user(self._user_with_roles("fleet-gate-norole@test.local", ["Internal Auditor"]))
        try:
            ctx = fleet.get_context(frappe._dict())
            self.assertFalse(ctx.has_fleet_role, "a non-fleet user must not pass the gate")
            self.assertIsNone(ctx.get("csrf_token"), "no CSRF token may be issued to a non-fleet user")
        finally:
            frappe.set_user("Administrator")

    def test_fleet_role_gets_access_and_csrf(self):
        frappe.set_user(self._user_with_roles("fleet-gate-mgr@test.local", ["Fleet Manager"]))
        try:
            ctx = fleet.get_context(frappe._dict())
            self.assertTrue(ctx.has_fleet_role, "a Fleet Manager must pass the gate")
            self.assertTrue(ctx.get("csrf_token"), "a fleet user must receive a CSRF token")
        finally:
            frappe.set_user("Administrator")
