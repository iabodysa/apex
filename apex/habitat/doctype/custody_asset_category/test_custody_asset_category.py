# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase


def _category(**overrides):
    fields = {
        "doctype": "Custody Asset Category",
        "category_name": "_T-Category " + frappe.generate_hash(length=6),
    }
    fields.update(overrides)
    return frappe.get_doc(fields)


class TestCategoryNameIsTheRecordName(FrappeTestCase):
    def test_the_category_name_becomes_the_record_name(self):
        doc = _category().insert(ignore_permissions=True)
        self.assertEqual(doc.name, doc.category_name)

    def test_framework_refuses_a_second_category_carrying_the_same_name(self):
        first = _category().insert(ignore_permissions=True)
        with self.assertRaises((frappe.DuplicateEntryError, frappe.UniqueValidationError)):
            _category(category_name=first.category_name).insert(ignore_permissions=True)

    def test_the_naming_field_refuses_to_be_empty(self):
        with self.assertRaisesRegex(frappe.ValidationError, "Category Name is required"):
            _category(category_name=None).insert(ignore_permissions=True)


class TestCategoryDepreciationPolicy(FrappeTestCase):
    def test_framework_refuses_a_depreciation_policy_that_does_not_exist(self):
        with self.assertRaisesRegex(frappe.LinkValidationError, "Could not find"):
            _category(default_depreciation_policy="No Such Policy " + frappe.generate_hash(length=6)).insert(
                ignore_permissions=True
            )

    def test_a_new_category_is_active_by_default_without_the_operator_saying_so(self):
        doc = _category().insert(ignore_permissions=True)
        self.assertEqual(doc.is_active, 1)
