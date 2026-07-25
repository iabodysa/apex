# Copyright (c) 2026, AFMCO Support Services Co. Ltd and Contributors
"""CSRF-token bootstrap guards for the portal shells.

The driver/Masar SPAs read ``window.csrf_token`` from the server-rendered host page
and frappe-ui attaches it as ``X-Frappe-CSRF-Token`` on every POST. Frappe's CSRF
guard (auth.validate_csrf_token) throws CSRFTokenError on a POST whose header does
not match the session's saved token — so an empty/absent token at boot breaks the
SPA's first call.

Masar: www/masar.py previously swallowed get_csrf_token() into "" via a blanket
``except Exception``. get_csrf_token() mints a token even for Guest, so it never
legitimately fails; the swallow only ever produced a silently-empty token that made
every Masar POST fail CSRF. These tests assert the rendered context carries a real
token (Guest and authenticated) and that the shell emits it as a non-empty JSON
string literal.

Driver: the driver host page must likewise expose a non-empty token, and the
bootstrap read get_driver_context must return a well-formed context without raising
(it is the SPA's first call; the GET/CSRF reconciliation lives in App.vue).

No secrets or PII — tokens here are framework-minted hashes for the test session.
"""

import os
import re

import frappe
from frappe.sessions import get_csrf_token
from frappe.tests.utils import FrappeTestCase

from apex.salis.api import driver_portal
from apex.www import driver as driver_page
from apex.www import masar as masar_page

# [#d2dz55]
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def _render_shell(page_module, html_name, ctx):
    """Render a real host page (driver.html / masar.html) through Frappe's Jinja env
    so the template's ``tojson`` filter and autoescape-off www behaviour are exercised."""
    html_path = os.path.join(os.path.dirname(page_module.__file__), html_name)
    with open(html_path, encoding="utf-8") as fh:
        template = fh.read()
    return frappe.render_template(template, dict(ctx))


class TestMasarCsrfToken(FrappeTestCase):
    """The Masar context token is real, never the swallowed empty string."""

    def tearDown(self):
        frappe.local.form_dict = frappe._dict()
        frappe.set_user("Administrator")

    def test_guest_context_has_nonempty_valid_token(self):
        # [#hk0xw6]
        frappe.set_user("Guest")
        frappe.local.form_dict = frappe._dict()
        ctx = masar_page.get_context(frappe._dict())
        self.assertTrue(ctx.csrf_token, "masar guest csrf_token must not be empty")
        self.assertRegex(ctx.csrf_token, _TOKEN_RE)

    def test_authenticated_context_has_nonempty_valid_token(self):
        frappe.set_user("Administrator")
        frappe.local.form_dict = frappe._dict()
        ctx = masar_page.get_context(frappe._dict())
        self.assertTrue(ctx.csrf_token)
        self.assertRegex(ctx.csrf_token, _TOKEN_RE)

    def test_rendered_shell_emits_nonempty_csrf_literal(self):
        frappe.set_user("Guest")
        frappe.local.form_dict = frappe._dict()
        ctx = masar_page.get_context(frappe._dict())
        html = _render_shell(masar_page, "masar.html", ctx)
        # [#abfywq]
        m = re.search(r'window\.csrf_token = "([^"]*)";', html)
        self.assertIsNotNone(m, "csrf_token assignment missing from masar shell")
        self.assertNotEqual(m.group(1), "", "masar shell emitted an empty csrf_token")


class TestDriverCsrfToken(FrappeTestCase):
    """The driver host page exposes a real token and the bootstrap read works."""

    def setUp(self):
        frappe.set_user("Administrator")

    def test_context_has_nonempty_valid_token(self):
        # [#7edqup]
        ctx = driver_page.get_context(frappe._dict())
        self.assertTrue(ctx.csrf_token, "driver csrf_token must not be empty")
        self.assertRegex(ctx.csrf_token, _TOKEN_RE)

    def test_rendered_shell_emits_nonempty_csrf_literal(self):
        ctx = driver_page.get_context(frappe._dict())
        html = _render_shell(driver_page, "driver.html", ctx)
        m = re.search(r'window\.csrf_token = "([^"]*)";', html)
        self.assertIsNotNone(m, "csrf_token assignment missing from driver shell")
        self.assertNotEqual(m.group(1), "", "driver shell emitted an empty csrf_token")

    def test_get_driver_context_returns_context_without_raising(self):
        # [#tgxx9o]
        result = driver_portal.get_driver_context()
        self.assertIn("enabled", result)
        self.assertIn("linked", result)
        self.assertIn("driver", result)

    def test_session_token_matches_emitted_token(self):
        # [#px4xxc]
        ctx = driver_page.get_context(frappe._dict())
        self.assertEqual(ctx.csrf_token, get_csrf_token())
