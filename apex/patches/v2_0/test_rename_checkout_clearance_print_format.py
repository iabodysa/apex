# Copyright (c) 2026, AFMCO and contributors
"""Guard for the checkout-clearance Print Format rename.

The patch is a one-liner, so what needs proving is not the rename itself but the three
states it has to survive without damage: an upgrading site that still holds the old key,
a site that has already run it (or a fresh install, which never had the old key), and
the split-brain site holding BOTH keys, where merging would silently destroy one row.

The idempotence proof runs the patch TWICE on the same fixture and reads the ROW back,
not the return value: a patch that raised on its second run, or that quietly re-created
the old key, would look identical from the outside otherwise.

The last test is about the shipped tree rather than the DB. A rename patch and the
record's own JSON are one indivisible change -- ``import_doc`` resolves the record by
the JSON's ``name`` and delete+inserts it (frappe/modules/import_file.py:230-231, :239),
so a patch shipped beside a JSON that still carries the old key would be undone by the
very next migrate. Asserting the two agree is what makes that impossible to ship.
"""

from __future__ import annotations

import json
import os

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.patches.v2_0.rename_checkout_clearance_print_format import (
    DOCTYPE,
    NEW,
    OLD,
    execute,
)

_HERE = os.path.dirname(os.path.abspath(__file__))
# apex/patches/v2_0 -> apex/patches -> apex
_APP_ROOT = os.path.dirname(os.path.dirname(_HERE))
_SHIPPED_JSON = os.path.join(
    _APP_ROOT, "habitat", "print_format", "housing_checkout_clearance",
    "housing_checkout_clearance.json",
)


class TestRenameCheckoutClearancePrintFormat(FrappeTestCase):
    def _print_format(self, name):
        """A non-standard Print Format under ``name``, so the fixture never collides
        with the standard record the app ships."""
        doc = frappe.get_doc(
            {
                "doctype": DOCTYPE,
                "name": name,
                "doc_type": "Housing Checkout",
                "module": "Habitat",
                "print_format_type": "Jinja",
                "custom_format": 1,
                "standard": "No",
                "html": "<h1>fixture</h1>",
            }
        )
        doc.insert(ignore_permissions=True)
        self.addCleanup(
            lambda: frappe.db.delete(DOCTYPE, {"name": ["in", [OLD, NEW]]})
        )
        return doc

    def _drop_both(self):
        frappe.db.delete(DOCTYPE, {"name": ["in", [OLD, NEW]]})

    def test_the_old_key_is_moved_and_running_twice_changes_nothing(self):
        self._drop_both()
        self._print_format(OLD)

        execute()
        self.assertFalse(
            frappe.db.exists(DOCTYPE, OLD), "the retired key survived the rename"
        )
        self.assertTrue(frappe.db.exists(DOCTYPE, NEW), "the renamed row is missing")

        execute()
        self.assertFalse(
            frappe.db.exists(DOCTYPE, OLD),
            "a second run re-created the retired key — the patch is not idempotent",
        )
        self.assertTrue(
            frappe.db.exists(DOCTYPE, NEW), "a second run lost the renamed row"
        )

    def test_a_site_without_the_old_key_is_left_alone(self):
        """A fresh install never had the old row, and must not gain one."""
        self._drop_both()
        execute()
        self.assertFalse(frappe.db.exists(DOCTYPE, OLD))
        self.assertFalse(
            frappe.db.exists(DOCTYPE, NEW),
            "the patch invented a row on a site that had neither key",
        )

    def test_both_keys_present_is_reported_rather_than_merged(self):
        """Merging would destroy one row, so the patch must leave both and log."""
        self._drop_both()
        self._print_format(OLD)
        self._print_format(NEW)

        execute()
        self.assertTrue(
            frappe.db.exists(DOCTYPE, OLD), "the split-brain row was silently destroyed"
        )
        self.assertTrue(frappe.db.exists(DOCTYPE, NEW))
        self.assertTrue(
            frappe.db.exists(
                "Error Log", {"error": ["like", f"%{OLD}%"]}
            ),
            "a skipped rename left no trace for the operator",
        )

    def test_the_shipped_json_carries_the_renamed_key(self):
        """Patch and JSON are one change: migrate re-imports by the JSON's name."""
        with open(_SHIPPED_JSON, encoding="utf-8") as fh:
            shipped = json.load(fh)
        self.assertEqual(
            shipped.get("name"),
            NEW,
            "the shipped print format JSON does not carry the renamed key, so the very "
            "next migrate would re-create the retired one beside it",
        )
