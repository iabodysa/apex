# Copyright (c) 2026, afmcoltd
"""Access gate of the /safety Safety Rounds portal (www/safety.py get_context).

The Safety Checklist portal is an admin-style surface, not a guest link, so its gate must
hold:
  * a Guest is redirected to /login (then back to /safety);
  * a logged-in user WITHOUT a portal role is bootstrapped with NO capabilities, so the
    shell renders the friendly no-role screen and every guarded call is refused;
  * a user holding any merged-portal role is bootstrapped WITH capabilities.

THE GATE MOVED, AND THIS FILE FOLLOWED IT. It used to assert ``ctx.has_portal_role`` and
"no csrf_token for a user without the role". Neither exists now: every portal door goes
through ``publish_portal_context``, which issues the CSRF token to every AUTHENTICATED
caller as part of the shared shell and expresses the gate as
``boot["apex_portal"]["capabilities"]`` — an empty list for a user the role check refused.
Asserting the old field names against the current code would have passed on ``None`` while
proving nothing, which is what the pre-conversion form of this test did.

Safety Officer IS admitted: the merged portal grants what each role is asked to do, and a
maker who cannot submit records a round for a supervisor to close rather than being turned
away at the door.

The identities come from ``apex.tests._helpers._user`` — the shared get-or-create — instead
of a private copy of the same User builder, and ``as_user`` restores the session user
rather than a try/finally in every case.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.tests._helpers import _user, as_user
from apex.www import safety


def capabilities_of(context):
    return context.boot["apex_portal"]["capabilities"]


class TestSafetyPageAccessGate(FrappeTestCase):
    def setUp(self):
        # render_in_arabic() writes frappe.local.lang for the rest of the render. In a
        # request that local dies with the request; in a test run it does not, so it is
        # handed back rather than left for whatever runs next.
        self.addCleanup(setattr, frappe.local, "lang", frappe.local.lang)

    def test_guest_is_redirected_to_login(self):
        with as_user("Guest"):
            with self.assertRaises(frappe.Redirect):
                safety.get_context(frappe._dict())
            self.assertEqual(
                frappe.local.flags.redirect_location,
                "/login?redirect-to=/safety",
                "a Guest must be sent to login and back to /safety",
            )

    def test_non_safety_role_gets_no_capabilities(self):
        with as_user(_user("safety-gate-norole@test.local", "Internal Auditor")):
            ctx = safety.get_context(frappe._dict())
            self.assertEqual(
                capabilities_of(ctx), [], "a non-safety user must not pass the gate"
            )

    def test_safety_officer_is_admitted(self):
        # Reversed with the merged portal: Safety Officer is granted /safety, so refusing it
        # here asserted the very defect A-464 fixed — a role that reaches a portal it cannot
        # use. It is admitted, and records a round for a supervisor to close rather than
        # submitting one itself.
        with as_user(_user("safety-gate-officer@test.local", "Safety Officer")):
            ctx = safety.get_context(frappe._dict())
            self.assertTrue(
                capabilities_of(ctx), "Safety Officer is granted the safety portal"
            )

    def test_safety_role_gets_capabilities_and_csrf(self):
        with as_user(_user("safety-gate-mgr@test.local", "Accommodation Manager")):
            ctx = safety.get_context(frappe._dict())
            self.assertTrue(
                capabilities_of(ctx), "an Accommodation Manager must pass the gate"
            )
            self.assertTrue(ctx.csrf_token, "the portal's POSTs need a CSRF token")

    def test_the_safety_door_opens_on_the_rounds_route(self):
        """/safety and /housing are one app; the door decides where it lands."""
        with as_user(_user("safety-gate-mgr@test.local", "Accommodation Manager")):
            ctx = safety.get_context(frappe._dict())
            self.assertEqual(ctx.boot["apex_portal"]["initial_route"], "/rounds")
