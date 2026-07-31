# Copyright (c) 2026, AFMCO and contributors
"""The help re-seed must repair a drifted panel and write nothing on a second run.

Drift is the whole reason the patch exists, so the repair case seeds a wrong value
first rather than asserting against a site that already happens to be correct.
"""

from __future__ import annotations

from unittest import mock

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.patches.v2_1.refresh_integration_settings_help import DOCTYPE, HELP_FIELDS, execute


class TestRefreshIntegrationSettingsHelp(FrappeTestCase):
    def setUp(self):
        # A Single lives in tabSingles, outside any row this test created, and the
        # per-test rollback never reaches it - snapshot before the first write below.
        self._stored = {
            field: frappe.db.get_single_value(DOCTYPE, field, cache=False) for field in HELP_FIELDS
        }
        self.addCleanup(self._restore)

    def _restore(self):
        for field, value in self._stored.items():
            frappe.db.set_single_value(DOCTYPE, field, value)

    def _shipped(self, field):
        return frappe.get_meta(DOCTYPE).get_field(field).default

    def test_every_help_field_ships_a_default_to_seed_from(self):
        for field in HELP_FIELDS:
            self.assertTrue(self._shipped(field), f"{field} has no shipped default")

    def test_a_drifted_panel_is_reseeded(self):
        for field in HELP_FIELDS:
            frappe.db.set_single_value(DOCTYPE, field, "<p>advice from an older release</p>")
        execute()
        for field in HELP_FIELDS:
            self.assertEqual(
                frappe.db.get_single_value(DOCTYPE, field, cache=False), self._shipped(field)
            )

    def test_a_second_run_writes_nothing(self):
        execute()
        with mock.patch.object(frappe.db, "set_single_value") as writer:
            execute()
        writer.assert_not_called()
