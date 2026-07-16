# Copyright (c) 2026, AFMCO and contributors
"""Access gates of the two fleet surfaces (www/fleet.py + www/fleet_os.py).

The fleet redesign split one surface into two, each with its own gate:

  /fleet — the EMPLOYEE self-service page (my vehicle · fuel · my trips):
    * a Guest is redirected to /login (then back to /fleet);
    * ANY logged-in user may open it — no fleet role is required. A CSRF token
      is issued so the page's whitelisted POST (submit_fuel_request) passes the
      CSRF guard. Data is scoped PER-USER server-side, so opening it as an
      ordinary (non-fleet) employee can never leak another user's data.

  /fleet-os — the preserved SUPERVISOR board (an ADMIN surface, not a guest
  portal), which still gates on FLEET_ROLES:
    * a Guest is redirected to /login (then back to /fleet-os);
    * a logged-in user WITHOUT a fleet role gets the friendly no-role page —
      has_fleet_role is False and NO CSRF token is issued to them;
    * only a fleet-role user gets has_fleet_role True + a CSRF token for the
      board's whitelisted POSTs (reassign / stop / theft / workshop / recover).

A regression that issued the board's token (or has_fleet_role) to a non-fleet
user would expose the live fleet board; a regression that withheld /fleet's
token from an ordinary employee would break the employee page's fuel POST.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.www import fleet
from apex.www import fleet_os


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

    def test_employee_page_grants_any_logged_in_user_access_and_csrf(self):
        # [#n5wmeo] /fleet is the employee page: a non-fleet employee still gets
        # in (can_view) and a CSRF token for the fuel-request POST; per-user data
        # scoping — not a role gate — is what keeps one user off another's data.
        frappe.set_user(self._user_with_roles("fleet-gate-norole@test.local", ["Internal Auditor"]))
        try:
            ctx = fleet.get_context(frappe._dict())
            self.assertTrue(ctx.can_view, "any logged-in user may open the employee page")
            self.assertTrue(ctx.get("csrf_token"), "the employee page must issue a CSRF token for its fuel POST")
            self.assertIsNone(
                ctx.get("has_fleet_role"),
                "the employee page carries no role gate — has_fleet_role belongs to /fleet-os",
            )
        finally:
            frappe.set_user("Administrator")

    def test_board_non_fleet_role_gets_friendly_no_role_page(self):
        # The supervisor board at /fleet-os still gates on FLEET_ROLES.
        frappe.set_user(self._user_with_roles("fleet-gate-norole@test.local", ["Internal Auditor"]))
        try:
            ctx = fleet_os.get_context(frappe._dict())
            self.assertFalse(ctx.has_fleet_role, "a non-fleet user must not pass the board gate")
            self.assertIsNone(ctx.get("csrf_token"), "no CSRF token may be issued to a non-fleet user on the board")
        finally:
            frappe.set_user("Administrator")

    def test_board_fleet_role_gets_access_and_csrf(self):
        frappe.set_user(self._user_with_roles("fleet-gate-mgr@test.local", ["Fleet Manager"]))
        try:
            ctx = fleet_os.get_context(frappe._dict())
            self.assertTrue(ctx.has_fleet_role, "a Fleet Manager must pass the board gate")
            self.assertTrue(ctx.get("csrf_token"), "a fleet user must receive a CSRF token on the board")
        finally:
            frappe.set_user("Administrator")

    def test_board_guest_is_redirected_to_login(self):
        frappe.set_user("Guest")
        try:
            with self.assertRaises(frappe.Redirect):
                fleet_os.get_context(frappe._dict())
            self.assertEqual(
                frappe.local.flags.redirect_location,
                "/login?redirect-to=/fleet-os",
                "a Guest must be sent to login and back to /fleet-os",
            )
        finally:
            frappe.set_user("Administrator")
