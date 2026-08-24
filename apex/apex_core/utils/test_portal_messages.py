# Copyright (c) 2026, afmcoltd

from __future__ import annotations

from pathlib import Path

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import get_system_timezone

from apex.apex_core.utils.portal_bootstrap import publish_portal_context

_SHELL = Path(frappe.get_app_path("apex")) / "templates" / "includes" / "apex_portal_app.html"
_CONTRACT = '<script id="apex-portal-messages" type="application/json">{{ portal_messages | tojson }}</script>'


class TestPortalTranslationContract(FrappeTestCase):
    def setUp(self):
        super().setUp()
        self.addCleanup(setattr, frappe.local, "lang", frappe.local.lang)

    def _context(self, lang: str):
        frappe.local.lang = lang
        return publish_portal_context(
            frappe._dict(),
            entry="driver",
            public_path="/driver/",
            initial_route="/today",
            capabilities=(),
            subject=None,
        )

    def test_the_served_page_carries_the_dictionary_the_portal_reads(self):
        self.assertIn(_CONTRACT, _SHELL.read_text(encoding="utf-8"))

    def test_an_arabic_device_receives_the_arabic_for_a_portal_source_string(self):
        source = "Skip to content"
        messages = self._context("ar").portal_messages
        translated = messages.get(source)
        self.assertTrue(translated and translated != source)
        csv = (Path(frappe.get_app_path("apex")) / "translations" / "ar.csv").read_text(encoding="utf-8")
        self.assertIn(f"\n{source},{translated}\n", csv)

    def test_an_english_device_receives_no_arabic_and_falls_back_to_the_source(self):
        messages = self._context("en").portal_messages
        self.assertNotIn("Skip to content", messages)

    def test_the_page_turns_around_with_the_language_the_device_chose(self):
        arabic = self._context("ar").shell_meta
        self.assertEqual((arabic["language"], arabic["direction"]), ("ar", "rtl"))
        english = self._context("en").shell_meta
        self.assertEqual((english["language"], english["direction"]), ("en", "ltr"))

    def test_the_shell_renders_the_language_and_direction_it_is_given(self):
        markup = _SHELL.read_text(encoding="utf-8")
        self.assertIn(
            '<html lang="{{ shell_meta.language }}" dir="{{ shell_meta.direction }}"'
            ' data-timezone="{{ shell_meta.time_zone }}">',
            markup,
        )

    def test_the_shell_carries_the_time_zone_the_site_settled_on(self):
        self.assertEqual(self._context("ar").shell_meta["time_zone"], get_system_timezone())
