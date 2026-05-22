import frappe
import unittest
from frappe.tests.utils import FrappeTestCase


class TestDepreciationSnapshotItem(FrappeTestCase):

    def test_child_metadata(self):
        meta = frappe.get_meta("Depreciation Snapshot Item")
        self.assertEqual(meta.istable, 1)

    def test_row_in_memory(self):
        row = frappe.new_doc("Depreciation Snapshot Item")
        row.article = "test-art"
        row.original_cost_sar = 500
        self.assertEqual(row.doctype, "Depreciation Snapshot Item")

    def test_required_fields_defined(self):
        meta = frappe.get_meta("Depreciation Snapshot Item")
        field_names = [f.fieldname for f in meta.fields]
        self.assertIn("article", field_names)
        self.assertIn("original_cost_sar", field_names)
        self.assertTrue(len(field_names) > 0)
