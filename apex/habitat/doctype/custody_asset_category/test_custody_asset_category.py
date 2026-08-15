# Copyright (c) 2026, afmcoltd
"""Custody Asset Category's own contract: it is named by its category_name, and that name is unique.

The uniqueness case borrows the record from ``test_records.json`` rather than inserting one to
collide with — the fixture already stands, so the test asserts the rule instead of arranging it.
The previous form of this file built its own pair to collide and carried a sixteen-line
``test_ignore`` block for masters a category does not link to.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

test_dependencies = ["Custody Asset Category"]


class TestCustodyAssetCategory(FrappeTestCase):
    def test_a_category_is_named_by_its_category_name(self):
        category = frappe.get_doc({
            "doctype": "Custody Asset Category",
            "category_name": "_T Bedding",
        })
        category.insert(ignore_permissions=True)
        self.addCleanup(
            frappe.delete_doc, "Custody Asset Category", category.name,
            force=True, ignore_permissions=True,
        )

        self.assertEqual(category.name, "_T Bedding")

    def test_a_category_without_a_name_is_refused(self):
        category = frappe.get_doc({"doctype": "Custody Asset Category"})

        with self.assertRaises(frappe.exceptions.ValidationError):
            category.insert(ignore_permissions=True)

    def test_a_second_category_cannot_take_a_name_already_in_use(self):
        # _Test Custody Category comes from test_records.json, so the collision needs no arranging.
        duplicate = frappe.get_doc({
            "doctype": "Custody Asset Category",
            "category_name": "_Test Custody Category",
        })

        with self.assertRaises(frappe.DuplicateEntryError):
            duplicate.insert(ignore_permissions=True)
