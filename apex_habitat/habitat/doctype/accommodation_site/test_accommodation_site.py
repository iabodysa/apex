import frappe
from frappe.tests.utils import FrappeTestCase


class TestAccommodationSite(FrappeTestCase):

    def test_create_valid_site(self):
        doc = frappe.get_doc({
            "doctype": "Accommodation Site",
            "site_name": "QA Test Site",
            "city": "Riyadh",
            "status": "Active",
        })
        doc.insert(ignore_permissions=True)
        self.assertEqual(doc.site_name, "QA Test Site")
        frappe.delete_doc("Accommodation Site", doc.name, force=True, ignore_permissions=True)

    def test_missing_site_name_raises(self):
        doc = frappe.get_doc({
            "doctype": "Accommodation Site",
            "city": "Jeddah",
        })
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert(ignore_permissions=True)

    def test_duplicate_site_name_raises(self):
        doc1 = frappe.get_doc({"doctype": "Accommodation Site", "site_name": "QA Dup Site"})
        doc1.insert(ignore_permissions=True)
        doc2 = frappe.get_doc({"doctype": "Accommodation Site", "site_name": "QA Dup Site"})
        with self.assertRaises(Exception):
            doc2.insert(ignore_permissions=True)
        frappe.delete_doc("Accommodation Site", doc1.name, force=True, ignore_permissions=True)
