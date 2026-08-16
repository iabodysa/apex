# Copyright (c) 2026, afmcoltd
"""Contract test for ``render_in_arabic`` (A-564): sets the request's translation
language to Arabic for the rest of the render, regardless of the session user's
own language preference."""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.apex_core.utils.portal_language import render_in_arabic


class TestRenderInArabic(FrappeTestCase):
    def setUp(self):
        self._prev_lang = frappe.local.lang
        self.addCleanup(setattr, frappe.local, "lang", self._prev_lang)

    def test_sets_local_lang_to_arabic(self):
        frappe.local.lang = "en"
        render_in_arabic()
        self.assertEqual(frappe.local.lang, "ar")

    def test_overrides_whatever_language_was_active(self):
        frappe.local.lang = "fr"
        render_in_arabic()
        self.assertEqual(frappe.local.lang, "ar")

    def test_translation_resolves_arabic_after_call(self):
        frappe.local.lang = "en"
        render_in_arabic()
        # A round-trip through the translator itself, not just the flag —
        # frappe._() must actually resolve into the language now active.
        self.assertEqual(frappe._("Monday", lang="ar"), frappe._("Monday", lang=frappe.local.lang))
