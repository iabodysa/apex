# Copyright (c) 2026, AFMCO Support Services Co. Ltd and Contributors
"""Shared portal-bootstrap helpers + per-route smoke (T-646).

guest_redirect was extracted from the four www host pages (driver / masar / fleet /
safety). This pins the helper both ways (raises for Guest, no-ops otherwise) and
smokes each route's get_context so the dedupe stayed behaviour-preserving. Every
route now publishes its shell through publish_portal_context, so the smoke checks
the shared contract it actually returns — csrf_token, shell_meta and
boot["apex_portal"]["capabilities"] — rather than the page-specific appearance keys
and role booleans that contract replaced. The per-page role gates and csrf handling
are exercised by their own suites (test_portal_csrf_bootstrap, test_portal_xss) and
are deliberately not retested here.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.apex_core.utils.portal_bootstrap import guest_redirect
from apex.www import driver as driver_page
from apex.www import fleet as fleet_page
from apex.www import masar as masar_page
from apex.www import safety as safety_page


class TestGuestRedirect(FrappeTestCase):
    def tearDown(self):
        frappe.local.flags.redirect_location = None
        frappe.set_user("Administrator")

    def test_guest_is_redirected_to_login_with_return_path(self):
        frappe.set_user("Guest")
        with self.assertRaises(frappe.Redirect):
            guest_redirect("/driver")
        self.assertEqual(
            frappe.local.flags.redirect_location, "/login?redirect-to=/driver"
        )

    def test_authenticated_user_is_a_noop(self):
        frappe.set_user("Administrator")
        frappe.local.flags.redirect_location = None
        guest_redirect("/driver")
        self.assertIsNone(frappe.local.flags.redirect_location)


class TestRouteSmoke(FrappeTestCase):
    """Each get_context still returns the keys its shell renders from."""

    def tearDown(self):
        frappe.local.form_dict = frappe._dict()
        frappe.set_user("Administrator")

    def test_driver_context_keys(self):
        frappe.set_user("Administrator")
        ctx = driver_page.get_context(frappe._dict())
        self.assertTrue(ctx.csrf_token)
        self.assertTrue(ctx.shell_meta)
        self.assertIsInstance(ctx.boot["apex_portal"]["capabilities"], list)

    def test_masar_guest_context_keys(self):
        frappe.set_user("Guest")
        frappe.local.form_dict = frappe._dict()
        ctx = masar_page.get_context(frappe._dict())
        self.assertTrue(ctx.csrf_token)
        self.assertEqual(
            ctx.boot["apex_portal"]["capabilities"], [], "no worker token means no grants"
        )
        self.assertNotIn("masar_token", ctx, "the raw token must not be in the shell context")

    def test_driver_guest_context_keys(self):
        # A-046: /driver is a passwordless token portal (like /masar) —
        # guest-accessible, no login redirect. Capabilities stay empty until a valid
        # token cookie resolves a driver, and the raw token never leaks into the
        # shell context.
        frappe.set_user("Guest")
        frappe.local.form_dict = frappe._dict()
        ctx = driver_page.get_context(frappe._dict())
        self.assertTrue(ctx.csrf_token)
        self.assertEqual(
            ctx.boot["apex_portal"]["capabilities"], [], "no driver token means no grants"
        )
        self.assertNotIn("driver_token", ctx, "the raw token must not be in the shell context")

    def test_safety_context_role_gate_and_appearance(self):
        frappe.set_user("Administrator")
        ctx = safety_page.get_context(frappe._dict())
        self.assertTrue(
            ctx.boot["apex_portal"]["capabilities"], "System Manager must be admitted to /safety"
        )
        self.assertTrue(ctx.csrf_token)

    def test_fleet_context_grants_access_no_appearance(self):
        # /fleet is now the employee page: any logged-in user gets
        # fleet.self.read + csrf (no role gate; the FLEET_ROLES board moved to /fleet-os).
        frappe.set_user("Administrator")
        ctx = fleet_page.get_context(frappe._dict())
        self.assertIn("fleet.self.read", ctx.boot["apex_portal"]["capabilities"])
        self.assertTrue(ctx.csrf_token)
        self.assertIn("socketio_port", ctx.boot["apex_portal"])

    def test_guest_is_redirected_on_admin_routes(self):
        # /driver dropped from this list — A-046 made it a passwordless
        # token portal (guest-accessible, covered by test_driver_guest_context_keys).
        # fleet + safety remain login-gated admin routes.
        frappe.set_user("Guest")
        for page in (fleet_page, safety_page):
            with self.assertRaises(frappe.Redirect):
                page.get_context(frappe._dict())
