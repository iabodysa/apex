# Copyright (c) 2026, AFMCO Support Services Co. Ltd and Contributors
"""Stored / reflected XSS guards for the portal shells (T-658, T-661).

The four portal host pages (www/masar.html, driver.html, fleet.html, safety.html)
inject server values into inline <script>/<style> blocks, and the www renderer has
autoescape OFF — so a bare "{{ value }}" in a <script> is a raw-injection sink.

T-658 (reflected) — /masar forwards the request ``?w=<token>`` into the shell. A
hostile token such as ``";</script><script>alert(1)</script>`` must NOT close the
inline <script>: get_context charset-validates + escapes the token, and the
template emits every script value via ``tojson`` (JSON-encodes, escapes ``</`` and
quotes). This renders the real masar.html with a malicious token and asserts the
payload is inert.

T-661 (stored) — accent_color / brand_logo on the Salis Portal Theme are rendered
raw into the portal <style>/markup. validate() must reject a ``</style>``-bearing
accent and a non-/files logo, while accepting a legitimate hex colour and a real
uploaded file path.

Tests use synthetic payloads only.
"""

import os

import frappe
from frappe.tests.utils import FrappeTestCase

from apex_habitat.www import masar as masar_page

# A canonical reflected-XSS probe: it tries to break out of the quoted JS string
# AND close the surrounding <script> to start its own.
_XSS_W = '";</script><script>alert(1)</script>'


def _render_masar_shell(form_dict: dict) -> str:
	"""Build the /masar page context for ``form_dict`` and render the REAL
	masar.html through Frappe's Jinja env (so the template's ``tojson`` filter and
	the autoescape-off www behaviour are exercised, not mocked)."""
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

	def test_hostile_token_is_dropped_by_get_context(self):
		"""The charset guard reduces a non-token ?w= payload to "" at the source."""
		frappe.set_user("Guest")
		frappe.local.form_dict = frappe._dict(w=_XSS_W)
		try:
			ctx = masar_page.get_context(frappe._dict())
			# Not a valid token charset -> dropped before it can reach the shell.
			self.assertEqual(ctx.masar_token, "")
		finally:
			frappe.local.form_dict = frappe._dict()
			frappe.set_user("Administrator")

	def test_rendered_shell_has_no_breakout_from_the_param(self):
		"""End-to-end: render masar.html with the hostile token and assert the
		payload neither closes the inline <script> nor injects its own."""
		html, ctx = _render_masar_shell({"w": _XSS_W})
		# The dropped token is JSON-encoded (an empty string literal), never a bare
		# quoted interpolation that a payload could have escaped.
		self.assertIn('window.masar_token = "";', html)
		# The payload's script-breakout substrings must be absent from the output.
		self.assertNotIn("</script><script>alert(1)", html)
		self.assertNotIn("alert(1)", html)

	def test_legitimate_token_survives_and_is_json_encoded(self):
		"""A real hex-shaped token (frappe.generate_hash output) passes the charset
		guard and is emitted as a JSON string literal the SPA can read back."""
		token = "a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718"
		html, ctx = _render_masar_shell({"w": token})
		self.assertEqual(ctx.masar_token, token)
		self.assertIn('window.masar_token = "%s";' % token, html)

	def test_csrf_and_logo_are_json_encoded(self):
		"""csrf_token and portal_logo are emitted via tojson too (quoted JSON
		literals), not bare interpolations — the same sink the audit flagged."""
		html, ctx = _render_masar_shell({})
		# tojson always quotes a string value; a bare {{ }} would not guarantee it.
		self.assertIn("window.csrf_token = ", html)
		self.assertRegex(html, r'window\.csrf_token = "[^"]*";')
		self.assertRegex(html, r'window\.portal_logo = "[^"]*";')


class TestPortalThemeStoredXSS(FrappeTestCase):
	"""T-661 — validate() is the single source guard for the values projected into
	the portal <style>/<script>. Exercise the controller directly so the test
	targets the guard, not the field widget."""

	def setUp(self):
		frappe.set_user("Administrator")
		self.doc = frappe.get_single("Salis Portal Theme")
		self._orig_accent = self.doc.accent_color
		self._orig_logo = self.doc.brand_logo

	def tearDown(self):
		# Restore so the shared Single is left as found for other suites.
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
		# Keep logo blank/valid so only the accent is under test.
		self.doc.brand_logo = ""
		self.doc.validate()  # must not raise

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
		self.doc.validate()  # must not raise
