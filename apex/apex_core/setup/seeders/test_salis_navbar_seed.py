# Copyright (c) 2026, AFMCO and contributors
"""Tests for the Salis navbar Help-dropdown seeder.

Navbar Settings is a global Single a customer edits directly, so the seeder must
be strictly additive: a re-run over an already-seeded site must add nothing (the
non-vacuity control below proves it does add something when a link is actually
missing, so the idempotency assertion is not just "nothing ever happens").
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.apex_core.setup.seeders.salis_navbar_seed import (
    _LINKS,
    seed_salis_navbar_help_links,
)


class TestSalisNavbarSeed(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        settings = frappe.get_single("Navbar Settings")
        self._rows = [dict(r.as_dict()) for r in settings.help_dropdown]
        self.addCleanup(self._restore)

    def _restore(self):
        settings = frappe.get_single("Navbar Settings")
        settings.set("help_dropdown", self._rows)
        settings.save(ignore_permissions=True)
        frappe.db.commit()

    def _labels(self):
        return {
            row.item_label
            for row in frappe.get_single("Navbar Settings").help_dropdown
        }

    def test_all_configured_links_are_present_after_seeding(self):
        seed_salis_navbar_help_links()
        labels = self._labels()
        for link in _LINKS:
            self.assertIn(link["item_label"], labels)

    def test_reseeding_an_already_seeded_site_adds_no_duplicate_rows(self):
        seed_salis_navbar_help_links()
        before = len(frappe.get_single("Navbar Settings").help_dropdown)
        seed_salis_navbar_help_links()
        after = len(frappe.get_single("Navbar Settings").help_dropdown)
        self.assertEqual(before, after)

    def test_a_manually_removed_link_is_added_back_by_the_next_run(self):
        """Non-vacuity control: the seeder does add a genuinely-missing link, so
        the idempotency test above is not vacuously true."""
        settings = frappe.get_single("Navbar Settings")
        target = _LINKS[0]["item_label"]
        settings.set(
            "help_dropdown",
            [row for row in settings.help_dropdown if row.item_label != target],
        )
        settings.save(ignore_permissions=True)
        self.assertNotIn(target, self._labels())

        seed_salis_navbar_help_links()
        self.assertIn(target, self._labels())
