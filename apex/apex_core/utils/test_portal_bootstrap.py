# Copyright (c) 2026, AFMCO Support Services Co. Ltd and Contributors
"""Shared portal-bootstrap helpers + per-route smoke (T-646).

apply_portal_appearance / guest_redirect were extracted from the four www host
pages (driver / masar / fleet / safety). These tests pin the helpers BOTH ways
(appearance sets every key; guest_redirect raises for Guest, no-ops otherwise) and
smoke each route's get_context so the dedupe stayed behaviour-preserving. The
per-page role gates and csrf handling are exercised by their own suites
(test_portal_csrf_bootstrap, test_portal_xss) and are deliberately not retested here.

No secrets or PII — appearance values are framework defaults for the test session.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.apex_core.utils.portal_bootstrap import (
	apply_portal_appearance,
	guest_redirect,
)
from apex.www import driver as driver_page
from apex.www import fleet as fleet_page
from apex.www import masar as masar_page
from apex.www import safety as safety_page

_APPEARANCE_KEYS = ("portal_theme", "portal_accent", "portal_logo", "portal_show_brand")


class TestApplyPortalAppearance(FrappeTestCase):
	def test_sets_every_appearance_key(self):
		ctx = frappe._dict()
		apply_portal_appearance(ctx)
		for key in _APPEARANCE_KEYS:
			self.assertIn(key, ctx, f"{key} not projected onto context")
		# [#m513nt]
		self.assertTrue(ctx.portal_theme)
		self.assertIsInstance(ctx.portal_show_brand, bool)


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
		guest_redirect("/driver")  # [#3vfaf1]
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
		for key in _APPEARANCE_KEYS:
			self.assertIn(key, ctx)

	def test_masar_guest_context_keys(self):
		# [#h1uj6r]
		frappe.set_user("Guest")
		frappe.local.form_dict = frappe._dict()
		ctx = masar_page.get_context(frappe._dict())
		self.assertTrue(ctx.csrf_token)
		self.assertIn("masar_has_token", ctx)
		self.assertNotIn("masar_token", ctx, "the raw token must not be in the shell context")
		for key in _APPEARANCE_KEYS:
			self.assertIn(key, ctx)

	def test_driver_guest_context_keys(self):
		# [#drv1gu] A-046: /driver is a passwordless token portal (like /masar) —
		# guest-accessible, no login redirect. It projects driver_has_token from the
		# httpOnly cookie and never leaks the raw token into the shell context.
		frappe.set_user("Guest")
		frappe.local.form_dict = frappe._dict()
		ctx = driver_page.get_context(frappe._dict())
		self.assertTrue(ctx.csrf_token)
		self.assertIn("driver_has_token", ctx)
		self.assertNotIn("driver_token", ctx, "the raw token must not be in the shell context")
		for key in _APPEARANCE_KEYS:
			self.assertIn(key, ctx)

	def test_safety_context_role_gate_and_appearance(self):
		# [#4l0371]
		frappe.set_user("Administrator")
		ctx = safety_page.get_context(frappe._dict())
		self.assertTrue(ctx.has_safety_role)
		self.assertTrue(ctx.csrf_token)
		for key in _APPEARANCE_KEYS:
			self.assertIn(key, ctx)

	def test_fleet_context_grants_access_no_appearance(self):
		# [#p8eeoq] /fleet is now the employee page: any logged-in user gets
		# can_view + csrf (no role gate; the FLEET_ROLES board moved to /fleet-os).
		frappe.set_user("Administrator")
		ctx = fleet_page.get_context(frappe._dict())
		self.assertTrue(ctx.can_view)
		self.assertTrue(ctx.csrf_token)
		self.assertNotIn("has_fleet_role", ctx)
		self.assertIn("socketio_port", ctx)
		self.assertNotIn("portal_theme", ctx)

	def test_guest_is_redirected_on_admin_routes(self):
		# [#fqysuh] /driver dropped from this list — A-046 made it a passwordless
		# token portal (guest-accessible, covered by test_driver_guest_context_keys).
		# fleet + safety remain login-gated admin routes.
		frappe.set_user("Guest")
		for page in (fleet_page, safety_page):
			with self.assertRaises(frappe.Redirect):
				page.get_context(frappe._dict())
