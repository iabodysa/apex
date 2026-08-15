# Copyright (c) 2026, afmcoltd
"""Access gates of the two fleet surfaces (www/fleet.py + www/fleet_os.py).

The fleet redesign split one surface into two, each with its own gate:

  /fleet — the EMPLOYEE self-service page (my vehicle · fuel · my trips):
    * a Guest is redirected to /login (then back to /fleet);
    * ANY logged-in user may open it — no fleet role is required, and the shell is handed
      ``fleet.self.read``. Data is scoped PER-USER server-side, so opening it as an ordinary
      (non-fleet) employee can never leak another user's data.

  /fleet-os — the preserved SUPERVISOR board (an ADMIN surface, not a guest portal), which
  still gates on FLEET_ROLES:
    * a Guest is redirected to /login (then back to /fleet-os);
    * a logged-in user WITHOUT a fleet role gets NO capabilities, so the shell renders the
      friendly no-role screen;
    * only a fleet-role user is handed ``fleet.operations.read``.

A regression that handed the board's operations capability to a non-fleet user would expose
the live fleet board; a regression that withheld ``fleet.self.read`` from an ordinary
employee would break the employee page.

THE GATE MOVED, AND THIS FILE FOLLOWED IT — see test_safety_page_access_gate for why
``can_view`` / ``has_fleet_role`` and the conditional CSRF token are gone and
``boot["apex_portal"]["capabilities"]`` is what now carries the verdict. The two surfaces
are separated here by the capability NAMESPACE they grant, which is the distinction the
board's own API reads.

The identities come from ``apex.tests._helpers._user`` — the shared get-or-create — instead
of a private copy of the same User builder.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.tests._helpers import _user, as_user
from apex.www import fleet, fleet_os


def capabilities_of(context):
    return context.boot["apex_portal"]["capabilities"]


class TestFleetPageAccessGate(FrappeTestCase):
    def setUp(self):
        # render_in_arabic() writes frappe.local.lang for the rest of the render; handed
        # back here because in a test run that local outlives the case.
        self.addCleanup(setattr, frappe.local, "lang", frappe.local.lang)

    def test_guest_is_redirected_to_login(self):
        with as_user("Guest"):
            with self.assertRaises(frappe.Redirect):
                fleet.get_context(frappe._dict())
            self.assertEqual(
                frappe.local.flags.redirect_location,
                "/login?redirect-to=/fleet",
                "a Guest must be sent to login and back to /fleet",
            )

    def test_employee_page_grants_any_logged_in_user_access_and_csrf(self):
        # /fleet is the employee page: a non-fleet employee still gets in, and per-user data
        # scoping — not a role gate — is what keeps one user off another's data.
        with as_user(_user("fleet-gate-norole@test.local", "Internal Auditor")):
            ctx = fleet.get_context(frappe._dict())
            self.assertIn(
                "fleet.self.read",
                capabilities_of(ctx),
                "any logged-in user may open the employee page",
            )
            self.assertTrue(ctx.csrf_token, "the employee page's POSTs need a CSRF token")
            self.assertNotIn(
                "fleet.operations.read",
                capabilities_of(ctx),
                "the employee page never grants the supervisor board's capability",
            )

    def test_board_non_fleet_role_gets_no_capabilities(self):
        # The supervisor board at /fleet-os still gates on FLEET_ROLES.
        with as_user(_user("fleet-gate-norole@test.local", "Internal Auditor")):
            ctx = fleet_os.get_context(frappe._dict())
            self.assertEqual(
                capabilities_of(ctx), [], "a non-fleet user must not pass the board gate"
            )

    def test_board_fleet_role_gets_access_and_csrf(self):
        with as_user(_user("fleet-gate-mgr@test.local", "Fleet Manager")):
            ctx = fleet_os.get_context(frappe._dict())
            self.assertIn(
                "fleet.operations.read",
                capabilities_of(ctx),
                "a Fleet Manager must pass the board gate",
            )
            self.assertTrue(ctx.csrf_token, "a fleet user must receive a CSRF token")

    def test_board_guest_is_redirected_to_login(self):
        with as_user("Guest"):
            with self.assertRaises(frappe.Redirect):
                fleet_os.get_context(frappe._dict())
            self.assertEqual(
                frappe.local.flags.redirect_location,
                "/login?redirect-to=/fleet-os",
                "a Guest must be sent to login and back to /fleet-os",
            )
