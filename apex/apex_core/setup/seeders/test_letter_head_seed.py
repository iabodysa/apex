# Copyright (c) 2026, AFMCO and contributors
"""Tests for the Letter Head seeder's HTML builders and idempotency guard.

``_header_html`` / ``_footer_html`` are pure functions of a company identity dict,
each line conditional on the corresponding field being set (an unregistered
company with no tax id must not print a blank "Tax ID:" line). ``seed_letter_head``
must not overwrite an existing "Apex" Letter Head -- the seeder's own docstring
says a customer who edited theirs keeps it, so a re-run must be a true no-op.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.apex_core.setup.seeders.letter_head_seed import (
    LETTER_HEAD_NAME,
    _footer_html,
    _header_html,
    seed_letter_head,
)


class TestLetterHeadHtmlBuilders(FrappeTestCase):
    def test_header_includes_name_address_and_tax_id_when_all_set(self):
        identity = frappe._dict(name="Apex Co", address="Riyadh, KSA", tax_id="12345")
        html = _header_html(identity)
        self.assertIn("Apex Co", html)
        self.assertIn("Riyadh, KSA", html)
        self.assertIn("12345", html)

    def test_header_omits_the_address_line_when_address_is_blank(self):
        identity = frappe._dict(name="Apex Co", address="", tax_id="12345")
        html = _header_html(identity)
        self.assertIn("Apex Co", html)
        self.assertNotIn('margin-top:2px', html)  # the address line's own style marker

    def test_header_omits_the_tax_id_line_when_tax_id_is_blank(self):
        identity = frappe._dict(name="Apex Co", address="Riyadh, KSA", tax_id="")
        html = _header_html(identity)
        self.assertNotIn("Tax ID", html)

    def test_footer_joins_phone_and_email_with_a_separator(self):
        identity = frappe._dict(phone="0500000000", email="ops@example.com")
        html = _footer_html(identity)
        self.assertIn("0500000000", html)
        self.assertIn("ops@example.com", html)
        self.assertIn("·", html)  # the middle-dot separator

    def test_footer_with_only_a_phone_omits_the_separator(self):
        identity = frappe._dict(phone="0500000000", email="")
        html = _footer_html(identity)
        self.assertIn("0500000000", html)
        self.assertNotIn("·", html)


class TestSeedLetterHeadIdempotency(FrappeTestCase):
    def test_a_second_run_does_not_touch_an_existing_letter_head(self):
        self.assertTrue(
            frappe.db.exists("Letter Head", LETTER_HEAD_NAME),
            "the Apex Letter Head must already be seeded by after_install/after_migrate "
            "on any provisioned test site -- this pins that seed_letter_head is a no-op "
            "once it exists, not that it never ran.",
        )
        before = frappe.db.get_value("Letter Head", LETTER_HEAD_NAME, "content")
        seed_letter_head()
        after = frappe.db.get_value("Letter Head", LETTER_HEAD_NAME, "content")
        self.assertEqual(before, after)
