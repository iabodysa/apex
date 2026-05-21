import frappe
import unittest
from frappe.tests.utils import FrappeTestCase


class TestCustodyReturnItem(FrappeTestCase):

    def test_child_metadata(self):
        meta = frappe.get_meta("Custody Return Item")
        self.assertEqual(meta.istable, 1)

    def test_row_in_memory(self):
        row = frappe.new_doc("Custody Return Item")
        row.article = "test-art"
        row.qty = 1
        self.assertEqual(row.doctype, "Custody Return Item")

    def test_required_fields_defined(self):
        meta = frappe.get_meta("Custody Return Item")
        field_names = [f.fieldname for f in meta.fields]
        self.assertIn("article", field_names)
        self.assertIn("qty", field_names)
        self.assertTrue(len(field_names) > 0)
