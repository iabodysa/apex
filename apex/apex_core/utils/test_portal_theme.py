# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.apex_core.utils.portal_bootstrap import (
    _DEFAULT_THEME_COLOR,
    build_portal_shell_meta,
    portal_seed_color,
)

_APPEARANCE = ("accent_color", "brand_logo", "show_brand")


class TestPortalThemeSeed(FrappeTestCase):
    def setUp(self):
        super().setUp()
        settings = frappe.get_single("Salis Settings")
        restore = {field: settings.get(field) for field in _APPEARANCE}
        self.addCleanup(frappe.db.set_value, "Salis Settings", "Salis Settings", restore)

    def _appearance(self, **values):
        frappe.db.set_value("Salis Settings", "Salis Settings", values)

    def _meta(self):
        return build_portal_shell_meta(entry="driver", public_path="/driver/")

    def test_the_saved_seed_reaches_the_shell_and_the_browser_chrome(self):
        self._appearance(accent_color="#123456")
        meta = self._meta()
        self.assertEqual(meta["seed_color"], "#123456")
        self.assertEqual(meta["theme_color"], "#123456")

    def test_a_blank_seed_leaves_the_shell_with_no_override(self):
        self._appearance(accent_color="")
        meta = self._meta()
        self.assertEqual(meta["seed_color"], "")
        self.assertEqual(meta["theme_color"], _DEFAULT_THEME_COLOR)

    def test_a_value_that_is_not_a_hex_colour_never_reaches_the_style_block(self):
        for hostile in ("red", "rgb(1,2,3)", "#00844e;} body{display:none", "url(x)"):
            self.assertEqual(portal_seed_color(hostile), "")

    def test_the_settings_refuse_a_colour_the_portal_cannot_render(self):
        settings = frappe.get_single("Salis Settings")
        settings.accent_color = "rgb(1, 2, 3)"
        with self.assertRaises(frappe.ValidationError):
            settings.save()

    def test_the_tenant_logo_is_withheld_while_the_brand_is_switched_off(self):
        self._appearance(brand_logo="/files/tenant.png", show_brand=0)
        self.assertEqual(self._meta()["brand_logo"], "")
        self.assertFalse(self._meta()["show_brand"])
        self._appearance(show_brand=1)
        self.assertEqual(self._meta()["brand_logo"], "/files/tenant.png")
