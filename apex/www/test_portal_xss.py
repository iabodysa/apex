# Copyright (c) 2026, AFMCO Support Services Co. Ltd and Contributors
"""Stored / reflected XSS guards for the portal shells.

The four portal host pages (www/masar.html, driver.html, fleet.html, safety.html)
inject server values into inline <script>/<style> blocks, and the www renderer has
autoescape OFF — so a bare "{{ value }}" in a <script> is a raw-injection sink.

Reflected — /masar receives the personal token in ``?w=<token>``. The token is
NOT inlined into the shell: masar.py:50-56 redirects on ANY ``?w=`` — cookieing the
value first when it both passes the charset guard and resolves to an active worker
(``:51-52``), and DELETING the cookie otherwise (``:54``) — so the secret leaves the URL
either way and no ``?w=`` value ever reaches a render.

Three cases here assert against the current sinks: the presence boolean is gone
(capabilities carry the verdict, not ``window.masar_has_token``), the redirect target is
``/masar/`` with the trailing slash, and every server value leaves through a
``type="application/json"`` island rendered with ``tojson`` (apex_portal_app.html:31-33).
The security question these guard is unchanged.

Stored — accent_color / brand_logo on the Salis Portal Theme are rendered
raw into the portal <style>/markup. validate() must reject a ``</style>``-bearing
accent and a non-/files logo, while accepting a legitimate hex colour and a real
uploaded file path.

Tests use synthetic payloads only.
"""

import os

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.www import masar as masar_page

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

    def test_no_query_token_ever_reaches_a_render(self):
        """Hostile or well-formed, a ``?w=`` value is redirected away, never rendered.

        Both values are kept: the hostile one is the payload the audit flagged and it
        must not survive the charset guard; the hex-shaped one passes the guard, fails
        to resolve, and must still be redirected rather than rendered. Neither reaches
        publish_portal_context, so there is no sink for either to break out of.
        """
        for label, supplied in (
            ("a script-breakout payload", _XSS_W),
            ("a well-formed but unknown token", "a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4"),
        ):
            with self.subTest(query=label):
                frappe.set_user("Guest")
                frappe.local.form_dict = frappe._dict(w=supplied)
                try:
                    with self.assertRaises(frappe.Redirect):
                        masar_page.get_context(frappe._dict())
                    self.assertEqual(frappe.local.flags.redirect_location, "/masar/")
                finally:
                    frappe.local.form_dict = frappe._dict()
                    frappe.local.flags.redirect_location = None
                    frappe.set_user("Administrator")

    def test_rendered_shell_inlines_no_raw_token(self):
        """End-to-end: the clean /masar render carries no token sink of any spelling."""
        html, _ctx = _render_masar_shell({})
        self.assertNotIn("window.masar_token", html, "the raw token must never be inlined")
        self.assertNotIn("masar_wt", html, "the cookie name must not name a value in the page")
        self.assertNotIn(_XSS_W, html)

    def test_shell_sets_no_referrer_policy(self):
        """The page carries a no-referrer meta so the /masar?w=<token> URL never
		leaks the secret to a third party via the Referer header."""
        html, ctx = _render_masar_shell({})
        self.assertRegex(
            html,
            r'<meta\s+name="referrer"\s+content="no-referrer"\s*/?>',
            "masar shell must declare Referrer-Policy: no-referrer",
        )

    def test_every_server_value_leaves_through_a_json_island(self):
        """The sink the audit flagged: server values must be ``tojson``-encoded, not bare
        interpolations into executable script. All three now ride JSON islands, which a
        breakout payload cannot escape because the browser parses them as data."""
        html, _ctx = _render_masar_shell({})
        for island in ("apex-portal-bootstrap", "apex-portal-shell", "apex-csrf-token"):
            with self.subTest(island=island):
                self.assertRegex(
                    html,
                    rf'<script id="{island}" type="application/json">.+?</script>',
                    f"{island} is not emitted as a JSON island",
                )
        self.assertNotRegex(
            html,
            r"window\.\w+\s*=",
            "a server value is being assigned into executable script again",
        )


class TestPortalThemeStoredXSS(FrappeTestCase):
    """validate() is the single source guard for the values projected into
	the portal <style>/<script>. Exercise the controller directly so the test
	targets the guard, not the field widget."""

    def setUp(self):
        frappe.set_user("Administrator")
        self.doc = frappe.get_single("Driver Portal Theme")
        self._orig_accent = self.doc.accent_color
        self._orig_logo = self.doc.brand_logo

    def tearDown(self):
        self.doc.accent_color = self._orig_accent
        self.doc.brand_logo = self._orig_logo
        frappe.set_user("Administrator")

    # Two subTest runs cover one accent check, two payloads per branch. Safe to collapse
    # into subTests — validate() is called on an in-memory Single, nothing is saved and
    # the session user is not changed, so there is no per-test rollback for a subTest to
    # lose.
    def test_a_hostile_accent_is_refused(self):
        for accent in ("red;</style><script>x</script>", "url(javascript:alert(1))"):
            with self.subTest(accent=accent):
                self.doc.accent_color = accent
                with self.assertRaises(frappe.ValidationError):
                    self.doc.validate()

    def test_a_real_colour_accent_is_accepted(self):
        for accent in ("#0a84ff", "rgba(10, 132, 255, 0.5)"):
            with self.subTest(accent=accent):
                self.doc.accent_color = accent
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
        self.doc.validate()
