# Copyright (c) 2026, AFMCO and contributors
"""Guard for the five retired-name record renames.

What needs proving is not the rename call but the states it has to survive: an upgrading
site holding an old key, a site that already ran it (or a fresh install, which never had
one), and the split-brain site holding BOTH keys, where merging would destroy a row.

Idempotence is read off the ROW after running the patch twice, never off the return
value: a patch that raised on its second run, or quietly re-created the old key, looks
identical from outside otherwise.

The last two tests are about the shipped tree rather than the DB. A rename patch and the
record's own JSON are one indivisible change for anything migrate re-imports by name, so
a JSON still carrying the old key would be undone by the next migrate. And the Onboarding
Step entry must keep its force flag: that DocType ships no ``allow_rename``, so the plain
call is refused outright -- a fact worth pinning, because dropping the flag turns the
whole patch into a failed migrate rather than a skipped rename.
"""

from __future__ import annotations

import json
import os

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.patches.v2_0.rename_retired_habitat_record_names import RENAMES, execute

_HERE = os.path.dirname(os.path.abspath(__file__))
# apex/patches/v2_0 -> apex/patches -> apex
_APP_ROOT = os.path.dirname(os.path.dirname(_HERE))
_SHIPPED = {
    "Active Housing Assignments": ("number_card", "active_housing_assignments"),
    "Pending Housing Checkouts": ("number_card", "pending_housing_checkouts"),
    "Leases by Status": ("dashboard_chart", "leases_by_status"),
    "Record a Housing Assignment": ("onboarding_step", "record_a_housing_assignment"),
    "Lease Workflow": ("workflow", "lease_workflow"),
}


class TestRenameRetiredHabitatRecordNames(FrappeTestCase):
    def _chart(self, name):
        """A private Dashboard Chart under ``name``, so the fixture never collides with
        the standard record the app ships."""
        doc = frappe.get_doc(
            {
                "doctype": "Dashboard Chart",
                "name": name,
                "chart_name": name,
                # Group By, not Count: a Count chart demands a `based_on` date field
                # (dashboard_chart.py:401-402), which this fixture has no reason to carry.
                "chart_type": "Group By",
                "document_type": "Lease",
                "group_by_type": "Count",
                "group_by_based_on": "status",
                "type": "Donut",
                "is_public": 0,
                "is_standard": 0,
                "timeseries": 0,
                "filters_json": "[]",
            }
        )
        doc.insert(ignore_permissions=True)
        self.addCleanup(
            lambda: frappe.db.delete("Dashboard Chart", {"name": ["in", (name, "Leases by Status")]})
        )
        return doc

    def test_an_upgrading_site_keeps_one_row_under_the_new_key(self):
        frappe.db.delete("Dashboard Chart", {"name": "Leases by Status"})
        self._chart("Accommodation Leases by Status")

        execute()

        self.assertFalse(frappe.db.exists("Dashboard Chart", "Accommodation Leases by Status"))
        self.assertTrue(frappe.db.exists("Dashboard Chart", "Leases by Status"))

    def test_running_it_twice_leaves_the_same_single_row(self):
        frappe.db.delete("Dashboard Chart", {"name": "Leases by Status"})
        self._chart("Accommodation Leases by Status")

        execute()
        execute()

        self.assertFalse(frappe.db.exists("Dashboard Chart", "Accommodation Leases by Status"))
        self.assertTrue(frappe.db.exists("Dashboard Chart", "Leases by Status"))

    def test_a_site_holding_both_keys_loses_neither(self):
        frappe.db.delete("Dashboard Chart", {"name": "Leases by Status"})
        self._chart("Accommodation Leases by Status")
        self._chart("Leases by Status")

        execute()

        self.assertTrue(frappe.db.exists("Dashboard Chart", "Accommodation Leases by Status"))
        self.assertTrue(frappe.db.exists("Dashboard Chart", "Leases by Status"))

    def test_every_shipped_json_agrees_with_the_patch(self):
        for doctype, old, new, _force in RENAMES:
            with self.subTest(doctype=doctype):
                folder, slug = _SHIPPED[new]
                path = os.path.join(_APP_ROOT, "habitat", folder, slug, f"{slug}.json")
                shipped = json.loads(open(path, encoding="utf-8").read())
                self.assertEqual(
                    shipped["name"], new,
                    f"{path} still ships a key the patch does not rename to; migrate would "
                    "re-create the retired record beside the renamed one",
                )
                self.assertNotEqual(shipped["name"], old)

    def test_the_step_that_cannot_be_renamed_plainly_keeps_its_force_flag(self):
        forced = {new for _dt, _old, new, force in RENAMES if force}
        self.assertIn(
            "Record a Housing Assignment", forced,
            "Onboarding Step ships no allow_rename, so without force the rename throws "
            "and the migrate fails instead of skipping",
        )
        self.assertFalse(
            frappe.get_meta("Onboarding Step").allow_rename,
            "Onboarding Step now allows renaming, so the force flag is no longer the "
            "reason this entry differs — re-read the patch before trusting this list",
        )
