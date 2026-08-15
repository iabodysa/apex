# Copyright (c) 2026, afmcoltd
"""Access gate of the unified /housing portal (count + delivery flows).

The housing portal is an admin-style surface, not a guest link, so its gate must hold
(mirrors test_safety_page_access_gate):
  * a Guest is redirected to /login (then back to /housing);
  * a logged-in user WITHOUT a portal role is bootstrapped with NO capabilities;
  * a housing-role user is bootstrapped WITH capabilities and a CSRF token for the
    whitelisted submit_counts / pass_exit_* / confirm_receipt POSTs.

The count portal moved from /housing-count to /housing (the SPA now serves both the Housing
Inventory count and the Facility Asset Delivery clearance), so the gate that used to live on
www/housing_count.py now lives on www/housing.py and these assertions are re-homed onto it.
The import below is a regression guard: Frappe maps a route template to an UNDERSCORED
python module, and www/housing.py is already underscored, so it is always imported and
get_context always runs.

THE GATE MOVED, AND THIS FILE FOLLOWED IT — see test_safety_page_access_gate for why
``has_portal_role`` and the conditional CSRF token are gone and
``boot["apex_portal"]["capabilities"]`` is what now carries the verdict.

The identities come from ``apex.tests._helpers._user`` — the shared get-or-create — instead
of a private copy of the same User builder.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.tests._helpers import _user, as_user
from apex.www import housing


def capabilities_of(context):
    return context.boot["apex_portal"]["capabilities"]


class TestHousingPageAccessGate(FrappeTestCase):
    def setUp(self):
        # render_in_arabic() writes frappe.local.lang for the rest of the render; handed
        # back here because in a test run that local outlives the case.
        self.addCleanup(setattr, frappe.local, "lang", frappe.local.lang)

    def test_guest_is_redirected_to_login(self):
        with as_user("Guest"):
            with self.assertRaises(frappe.Redirect):
                housing.get_context(frappe._dict())
            self.assertEqual(
                frappe.local.flags.redirect_location,
                "/login?redirect-to=/housing",
                "a Guest must be sent to login and back to /housing",
            )

    def test_non_housing_role_gets_no_capabilities(self):
        with as_user(_user("housing-gate-norole@test.local", "Internal Auditor")):
            ctx = housing.get_context(frappe._dict())
            self.assertEqual(
                capabilities_of(ctx), [], "a non-housing user must not pass the gate"
            )

    def test_housing_role_gets_capabilities_and_csrf(self):
        with as_user(_user("housing-gate-mgr@test.local", "Accommodation Manager")):
            ctx = housing.get_context(frappe._dict())
            self.assertTrue(
                capabilities_of(ctx), "an Accommodation Manager must pass the gate"
            )
            self.assertTrue(ctx.csrf_token, "a housing user must receive a CSRF token")

    def test_system_manager_passes(self):
        ctx = housing.get_context(frappe._dict())
        self.assertTrue(capabilities_of(ctx), "a System Manager must pass the housing gate")

    def test_the_housing_door_does_not_land_on_the_safety_route(self):
        """The two doors share one app and one gate, but not one landing screen."""
        ctx = housing.get_context(frappe._dict())
        self.assertNotEqual(ctx.boot["apex_portal"]["initial_route"], "/rounds")
