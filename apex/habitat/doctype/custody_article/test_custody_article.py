# Copyright (c) 2026, afmcoltd
"""Custody Article's own contract: it needs a name and a category, and it takes the name it is given.

The category comes from its ``test_records.json``, so the link is really checked. The previous form
of this file pointed at a category named ``QA-CAT`` that has never existed on any site and passed
``ignore_links=True`` to stop Frappe noticing — which meant the "missing category" case could not
tell a missing link from a missing value. It also carried a sixteen-line ``test_ignore`` block to
stop Frappe building masters the article does not link to.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

test_dependencies = ["Custody Asset Category"]

CATEGORY = "_Test Custody Category"


class TestCustodyArticle(FrappeTestCase):
    def test_an_article_takes_the_name_it_is_given(self):
        article = frappe.get_doc({
            "doctype": "Custody Article",
            "article_name": "_T Mattress",
            "category": CATEGORY,
        })
        article.insert(ignore_permissions=True)
        self.addCleanup(
            frappe.delete_doc, "Custody Article", article.name, force=True, ignore_permissions=True
        )

        self.assertEqual(article.article_name, "_T Mattress")
        self.assertEqual(article.category, CATEGORY)

    def test_an_article_without_a_name_is_refused(self):
        article = frappe.get_doc({"doctype": "Custody Article", "category": CATEGORY})

        with self.assertRaises(frappe.exceptions.MandatoryError):
            article.insert(ignore_permissions=True)

    def test_an_article_without_a_category_is_refused(self):
        article = frappe.get_doc({"doctype": "Custody Article", "article_name": "_T Pillow"})

        with self.assertRaises(frappe.exceptions.MandatoryError):
            article.insert(ignore_permissions=True)

    def test_a_category_that_does_not_exist_is_silently_accepted(self):
        """Pinning what actually happens, which is not what the field says.

        ``category`` is a required Link, so a dangling value ought to be refused. It is not:
        ``depreciation_policy`` fetches from ``category.default_depreciation_policy``, so
        ``get_invalid_links`` takes the multi-value branch at
        frappe/model/base_document.py:836, where ``frappe.db.get_value(..., as_dict=True)``
        answers None for a row that is not there — and the ``if values:`` guard on line 848 then
        skips the invalid-link branch entirely. A Link with a ``fetch_from`` companion is
        therefore never checked. Asserting the refusal would fail; asserting the truth records the
        hole so the day it closes upstream, this case is what notices.
        """
        article = frappe.get_doc({
            "doctype": "Custody Article",
            "article_name": "_T Towel",
            "category": "_T Category That Does Not Exist",
        })
        article.insert(ignore_permissions=True)
        self.addCleanup(
            frappe.delete_doc, "Custody Article", article.name, force=True, ignore_permissions=True
        )

        self.assertFalse(frappe.db.exists("Custody Asset Category", "_T Category That Does Not Exist"))
