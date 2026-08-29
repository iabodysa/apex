# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase


def _policy():
    doc = frappe.get_doc({
        "doctype": "Operational Depreciation Policy",
        "policy_name": "_T-Policy " + frappe.generate_hash(length=6),
        "useful_life_years": 4,
    })
    return doc.insert(ignore_permissions=True)


def _category(**overrides):
    fields = {
        "doctype": "Custody Asset Category",
        "category_name": "_T-Category " + frappe.generate_hash(length=6),
    }
    fields.update(overrides)
    return frappe.get_doc(fields).insert(ignore_permissions=True)


def _article(**overrides):
    fields = {
        "doctype": "Custody Article",
        "article_name": "_T-Article " + frappe.generate_hash(length=6),
        "category": None,
    }
    fields.update(overrides)
    if not fields.get("category"):
        fields["category"] = _category().name
    return frappe.get_doc(fields)


class TestCustodyArticleCategory(FrappeTestCase):
    def test_framework_refuses_an_article_with_no_category(self):
        doc = frappe.get_doc({
            "doctype": "Custody Article",
            "article_name": "_T-Article " + frappe.generate_hash(length=6),
        })
        with self.assertRaises(frappe.MandatoryError):
            doc.insert(ignore_permissions=True)

    def test_framework_refuses_an_article_with_no_name(self):
        with self.assertRaises(frappe.MandatoryError):
            _article(article_name=None).insert(ignore_permissions=True)


class TestCustodyArticleDepreciationPolicy(FrappeTestCase):
    def test_framework_refuses_a_depreciation_policy_that_does_not_exist(self):
        with self.assertRaisesRegex(frappe.LinkValidationError, "Could not find"):
            _article(depreciation_policy="No Such Policy " + frappe.generate_hash(length=6)).insert(
                ignore_permissions=True
            )

    def test_the_policy_is_fetched_from_the_category_without_the_operator_naming_it(self):
        policy = _policy()
        category = _category(default_depreciation_policy=policy.name)
        doc = _article(category=category.name).insert(ignore_permissions=True)
        self.assertEqual(doc.depreciation_policy, policy.name)

    def test_a_category_with_no_policy_leaves_the_article_policy_empty(self):
        doc = _article().insert(ignore_permissions=True)
        self.assertFalse(doc.depreciation_policy)


class TestCustodyArticleNaming(FrappeTestCase):
    def test_the_article_is_named_by_its_article_name(self):
        doc = _article().insert(ignore_permissions=True)
        self.assertEqual(doc.name, doc.article_name)

    def test_the_declared_unit_of_measure_default_is_applied_server_side(self):
        doc = _article().insert(ignore_permissions=True)
        self.assertEqual(doc.unit_of_measure, "Each")
