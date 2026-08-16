# Copyright (c) 2026, afmcoltd

"""Tests for the Masar Supervisor portal page (``/masar-supervisor``).

``get_context`` and ``has_apps_screen_access`` had no test reaching them. The
generated shell template every www adapter shares
(``apex/templates/includes/apex_portal_app.html``) reads ``shell_meta.title``,
``shell_meta.canonical_path``, ``shell_meta.theme_color``,
``shell_meta.manifest_url``, ``shell_meta.apple_icon_url``, ``boot["apex_portal"]``,
``csrf_token`` and ``portal_messages`` off the context. These tests assert the
context carries every one of those keys and that the real template renders it
without a missing-key failure, then cover the apps-screen access gate the desk
tile's ``has_permission`` calls directly.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.tests._helpers import _user, as_user
from apex.www import masar_supervisor

_TEMPLATE_KEYS_ON_SHELL_META = ("title", "canonical_path", "manifest_url", "apple_icon_url", "theme_color")


def _render_shell(ctx):
    """Render the real generated-shell template through Frappe's Jinja env."""
    template_path = frappe.get_app_path("apex", "templates", "includes", "apex_portal_app.html")
    with open(template_path, encoding="utf-8") as fh:
        template = fh.read()
    return frappe.render_template(template, dict(ctx))


class TestMasarSupervisorContext(FrappeTestCase):
    """The context ``get_context`` publishes must carry every key the shared shell reads."""

    def setUp(self):
        """Runs every case as Administrator, regardless of what the previous case switched to."""
        frappe.set_user("Administrator")

    def tearDown(self):
        """Restores the Administrator session after a case that switched users."""
        frappe.set_user("Administrator")

    def test_context_carries_every_key_the_shell_template_reads(self):
        """shell_meta, boot, csrf_token and portal_messages must all be present and populated."""
        supervisor = _user("a564-masar-sup-context@test.local", "Fleet Supervisor")
        with as_user(supervisor):
            ctx = masar_supervisor.get_context(frappe._dict())

        self.assertTrue(ctx.csrf_token)
        self.assertIsNotNone(ctx.portal_messages)
        self.assertIn("apex_portal", ctx.boot)
        for key in _TEMPLATE_KEYS_ON_SHELL_META:
            self.assertIn(key, ctx.shell_meta, f"shell_meta is missing {key}, which the shell template reads")
        self.assertEqual(ctx.shell_meta["canonical_path"], "/masar-supervisor")

    def test_the_rendered_shell_does_not_fail_on_a_missing_key(self):
        """Rendering the actual shared template proves it finds every key it reads."""
        supervisor = _user("a564-masar-sup-render@test.local", "Fleet Supervisor")
        with as_user(supervisor):
            ctx = masar_supervisor.get_context(frappe._dict())

        html = _render_shell(ctx)
        self.assertIn("apex-portal-bootstrap", html)
        self.assertIn("apex-csrf-token", html)

    def test_an_admitted_role_is_handed_the_supervisor_capabilities(self):
        """A Fleet Supervisor's boot carries the fixed supervisor capability list."""
        supervisor = _user("a564-masar-sup-caps@test.local", "Fleet Supervisor")
        with as_user(supervisor):
            ctx = masar_supervisor.get_context(frappe._dict())

        self.assertEqual(
            sorted(ctx.boot["apex_portal"]["capabilities"]),
            sorted(masar_supervisor.SUPERVISOR_CAPABILITIES),
        )

    def test_a_refused_role_is_handed_no_capabilities(self):
        """A role outside SUPERVISOR_ROLES gets an empty capability list, never a KeyError."""
        outsider = _user("a564-masar-sup-refused@test.local", "Internal Auditor")
        with as_user(outsider):
            ctx = masar_supervisor.get_context(frappe._dict())

        self.assertEqual(ctx.boot["apex_portal"]["capabilities"], [])


class TestMasarSupervisorAppsScreenAccess(FrappeTestCase):
    """``has_apps_screen_access`` gates the /apps app-selector tile's ``has_permission``."""

    def setUp(self):
        """Runs every case as Administrator, regardless of what the previous case switched to."""
        frappe.set_user("Administrator")

    def tearDown(self):
        """Restores the Administrator session after a case that switched users."""
        frappe.set_user("Administrator")

    def test_a_supervisor_role_holder_sees_the_tile(self):
        """Every role in SUPERVISOR_ROLES must pass the gate."""
        for role in masar_supervisor.SUPERVISOR_ROLES:
            with self.subTest(role=role):
                holder = _user(f"a564-masar-tile-{role.split()[0].lower()}@test.local", role)
                with as_user(holder):
                    self.assertTrue(masar_supervisor.has_apps_screen_access())

    def test_a_role_outside_the_set_does_not_see_the_tile(self):
        """A real shipped role that holds none of SUPERVISOR_ROLES must be refused."""
        outsider = _user("a564-masar-tile-refused@test.local", "Internal Auditor")
        with as_user(outsider):
            self.assertFalse(masar_supervisor.has_apps_screen_access())
