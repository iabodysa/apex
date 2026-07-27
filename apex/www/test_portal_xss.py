# Copyright (c) 2026, AFMCO Support Services Co. Ltd and Contributors
"""Stored / reflected XSS guards for the portal shells (T-658, T-661).

The four portal host pages (www/masar.html, driver.html, fleet.html, safety.html)
inject server values into inline <script>/<style> blocks, and the www renderer has
autoescape OFF — so a bare "{{ value }}" in a <script> is a raw-injection sink.

T-658 (reflected) — /masar receives the personal token in ``?w=<token>``. After the
T-705/T-685 hardening the token is NO LONGER inlined into the shell: a valid-charset
token is dropped into an httpOnly cookie and the request is redirected to a clean
/masar (so the secret leaves the URL), while a hostile non-token ``?w=`` payload such
as ``";</script><script>alert(1)</script>`` fails the charset guard, is NOT written
to a cookie, triggers NO redirect, and never reaches the page. Either way the shell
inlines only a boolean (``window.masar_has_token``), so there is no token sink left in
the HTML for a payload to break out of.

T-661 (stored) — accent_color / brand_logo on the Salis Portal Theme are rendered
raw into the portal <style>/markup. validate() must reject a ``</style>``-bearing
accent and a non-/files logo, while accepting a legitimate hex colour and a real
uploaded file path.

Tests use synthetic payloads only.
"""

import os

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.www import masar as masar_page

# [#8cwasu]
_XSS_W = '";</script><script>alert(1)</script>'


def _render_masar_shell(form_dict: dict):
	"""Build the /masar page context for ``form_dict`` (with NO ?w=, the clean-URL
	state the shell actually renders) and render the REAL masar.html through Frappe's
	Jinja env, so the template's ``tojson`` filter and the autoescape-off www
	behaviour are exercised, not mocked. Returns ``(html, ctx)``."""
	frappe.set_user("Guest")
	frappe.local.form_dict = frappe._dict(form_dict)
	try:
		ctx = masar_page.get_context(frappe._dict())
		html_path = os.path.join(os.path.dirname(masar_page.__file__), "masar.html")
		with open(html_path, encoding="utf-8") as fh:
			template = fh.read()
		return frappe.render_template(template, dict(ctx)), ctx
	finally:
		frappe.local.form_dict = frappe._dict()
		frappe.set_user("Administrator")


class TestMasarReflectedXSS(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")

	def tearDown(self):
		frappe.local.form_dict = frappe._dict()
		frappe.set_user("Administrator")

	def test_hostile_token_is_dropped_and_does_not_redirect(self):
		"""A non-token ?w= payload fails the charset guard: it is NOT cookied, triggers
		NO redirect (the redirect only fires for a valid token), and the page falls
		through to the clean render with no link present."""
		frappe.set_user("Guest")
		frappe.local.form_dict = frappe._dict(w=_XSS_W)
		try:
			# [#rmp21g]
			ctx = masar_page.get_context(frappe._dict())
			# [#esx9v2]
			self.assertFalse(getattr(ctx, "masar_has_token", False))
			self.assertNotIn("masar_token", dict(ctx), "the raw token must not reach the shell context")
		finally:
			frappe.local.form_dict = frappe._dict()
			frappe.set_user("Administrator")

	def test_rendered_shell_inlines_no_raw_token(self):
		"""End-to-end: the clean /masar render inlines only the presence boolean, so
		there is no ``window.masar_token = "<secret>"`` sink in the HTML at all."""
		html, ctx = _render_masar_shell({})
		self.assertNotIn("window.masar_token", html, "the raw token must never be inlined")
		self.assertRegex(html, r"window\.masar_has_token = (true|false);")

	def test_valid_token_redirects_to_clean_url(self):
		"""A real hex-shaped token passes the charset guard and triggers the clean-URL
		redirect (the secret is moved off the query string, T-660/T-685) — it is never
		rendered into the shell."""
		token = "a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718"
		frappe.set_user("Guest")
		frappe.local.form_dict = frappe._dict(w=token)
		try:
			with self.assertRaises(frappe.Redirect):
				masar_page.get_context(frappe._dict())
			# [#9b9ppq]
			self.assertEqual(frappe.local.flags.redirect_location, "/masar")
		finally:
			frappe.local.form_dict = frappe._dict()
			frappe.local.flags.redirect_location = None
			frappe.set_user("Administrator")

	def test_shell_sets_no_referrer_policy(self):
		"""T-660: the page carries a no-referrer meta so the /masar?w=<token> URL never
		leaks the secret to a third party via the Referer header."""
		html, ctx = _render_masar_shell({})
		self.assertRegex(
			html,
			r'<meta\s+name="referrer"\s+content="no-referrer"\s*/?>',
			"masar shell must declare Referrer-Policy: no-referrer",
		)

	def test_csrf_and_logo_are_json_encoded(self):
		"""csrf_token and portal_logo are emitted via tojson too (quoted JSON
		literals), not bare interpolations — the same sink the audit flagged."""
		html, ctx = _render_masar_shell({})
		# [#m3h3gg]
		self.assertIn("window.csrf_token = ", html)
		self.assertRegex(html, r'window\.csrf_token = "[^"]*";')
		self.assertRegex(html, r'window\.portal_logo = "[^"]*";')


class TestPortalThemeStoredXSS(FrappeTestCase):
	"""T-661 — validate() is the single source guard for the values projected into
	the portal <style>/<script>. Exercise the controller directly so the test
	targets the guard, not the field widget."""

	def setUp(self):
		frappe.set_user("Administrator")
		self.doc = frappe.get_single("Driver Portal Theme")
		self._orig_accent = self.doc.accent_color
		self._orig_logo = self.doc.brand_logo

	def tearDown(self):
		# [#e6avg3]
		self.doc.accent_color = self._orig_accent
		self.doc.brand_logo = self._orig_logo
		frappe.set_user("Administrator")

	def test_style_breakout_accent_is_rejected(self):
		"""An accent that tries to close the <style> and open a <script> is refused."""
		self.doc.accent_color = "red;</style><script>x</script>"
		with self.assertRaises(frappe.ValidationError):
			self.doc.validate()

	def test_non_color_accent_is_rejected(self):
		self.doc.accent_color = "url(javascript:alert(1))"
		with self.assertRaises(frappe.ValidationError):
			self.doc.validate()

	def test_valid_hex_accent_passes(self):
		self.doc.accent_color = "#0a84ff"
		# [#lps769]
		self.doc.brand_logo = ""
		self.doc.validate()  # [#3vfaf1]

	def test_valid_rgb_accent_passes(self):
		self.doc.accent_color = "rgba(10, 132, 255, 0.5)"
		self.doc.brand_logo = ""
		self.doc.validate()

	def test_offsite_logo_is_rejected(self):
		self.doc.accent_color = ""
		self.doc.brand_logo = "https://evil.example/x.png"
		with self.assertRaises(frappe.ValidationError):
			self.doc.validate()

	def test_files_logo_passes(self):
		self.doc.accent_color = ""
		self.doc.brand_logo = "/files/logo.png"
		self.doc.validate()  # [#3vfaf1]
