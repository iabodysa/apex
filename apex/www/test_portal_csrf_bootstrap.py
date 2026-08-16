# Copyright (c) 2026, AFMCO Support Services Co. Ltd and Contributors
"""CSRF-token bootstrap guards for the portal shells.

The SPA reads its CSRF token from the server-rendered host page and frappe-ui attaches
it as ``X-Frappe-CSRF-Token`` on every POST. Frappe's CSRF guard
(auth.validate_csrf_token) throws CSRFTokenError on a POST whose header does not match
the session's saved token — so an empty/absent token at boot breaks the SPA's first call.

The shell does not write ``window.csrf_token = "…";``. Since the portals converged on one
Frappe-UI application, every www route is a 63-byte include of
``templates/includes/apex_portal_app.html``, which emits the token at :33 as
``&lt;script id="apex-csrf-token" type="application/json"&gt;{{ csrf_token | tojson }}&lt;/script&gt;``
— a JSON island, not a JS assignment, so these guards match against that tag.
``driver_portal.get_driver_context`` is retired and named as a FORBIDDEN symbol by
apex/www/test_portal_shell_contract.py, so no case here drives it.

Masar: ``get_csrf_token()`` mints a token even for Guest, so it never legitimately raises;
``www/masar.py`` must not swallow it behind a blanket ``except Exception``, because a
silently-empty token would fail every Masar POST's CSRF check. These tests assert the
rendered context carries a real token (Guest and authenticated) and that the shell emits
it as a non-empty JSON string literal.

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

from apex.www import driver as driver_page
from apex.www import masar as masar_page

_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]+$")
# The shared shell emits the token as a JSON island, not a JS assignment.
_EMITTED_RE = re.compile(
    r'<script id="apex-csrf-token" type="application/json">"([^"]*)"</script>'
)


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

    # One code path — publish_portal_context mints the token for every caller — driven
    # with two users across two page modules, kept as one subTest run so every distinct
    # (page, user) value executes.
    def test_every_portal_door_hands_the_shell_a_real_token(self):
        for page, name in ((masar_page, "masar"), (driver_page, "driver")):
            for user in ("Guest", "Administrator"):
                with self.subTest(page=name, user=user):
                    frappe.set_user(user)
                    frappe.local.form_dict = frappe._dict()
                    ctx = page.get_context(frappe._dict())
                    self.assertTrue(
                        ctx.csrf_token, f"{name} {user} csrf_token must not be empty"
                    )
                    self.assertRegex(ctx.csrf_token, _TOKEN_RE)
                    self.assertEqual(
                        ctx.csrf_token,
                        get_csrf_token(),
                        "the page handed the shell a token the session does not hold",
                    )

    def test_the_rendered_shell_emits_a_nonempty_csrf_island(self):
        for page, html_name in ((masar_page, "masar.html"), (driver_page, "driver.html")):
            with self.subTest(shell=html_name):
                frappe.set_user("Guest")
                frappe.local.form_dict = frappe._dict()
                ctx = page.get_context(frappe._dict())
                html = _render_shell(page, html_name, ctx)
                match = _EMITTED_RE.search(html)
                self.assertIsNotNone(
                    match, f"csrf token island missing from the {html_name} render"
                )
                self.assertNotEqual(
                    match.group(1), "", f"{html_name} emitted an empty csrf token"
                )
