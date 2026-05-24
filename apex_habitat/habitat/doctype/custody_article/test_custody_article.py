import frappe
from frappe.tests.utils import FrappeTestCase


class TestCustodyArticle(FrappeTestCase):

    def test_create_valid_article(self):
        doc = frappe.get_doc({
            "doctype": "Custody Article",
            "article_name": "QA Mattress",
            "category": "QA-CAT",
        })
        doc.insert(ignore_permissions=True)
        self.assertEqual(doc.article_name, "QA Mattress")
        frappe.delete_doc("Custody Article", doc.name, force=True, ignore_permissions=True)

    def test_missing_article_name_raises(self):
        doc = frappe.get_doc({
            "doctype": "Custody Article",
            "category": "QA-CAT",
        })
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert(ignore_permissions=True, ignore_links=True)

    def test_missing_category_raises(self):
        doc = frappe.get_doc({
            "doctype": "Custody Article",
            "article_name": "QA Pillow",
        })
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert(ignore_permissions=True, ignore_links=True)
