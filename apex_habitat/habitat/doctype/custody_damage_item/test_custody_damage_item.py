import frappe
import unittest
from frappe.tests.utils import FrappeTestCase


class TestCustodyDamageItem(FrappeTestCase):

    def test_child_metadata(self):
        meta = frappe.get_meta("Custody Damage Item")
        self.assertEqual(meta.istable, 1)

    def test_row_in_memory(self):
        row = frappe.new_doc("Custody Damage Item")
        row.article = "test-art"
        row.damage_description = "broken"
        row.estimated_replacement_cost_sar = 100
        self.assertEqual(row.doctype, "Custody Damage Item")

    def test_required_fields_defined(self):
        meta = frappe.get_meta("Custody Damage Item")
        field_names = [f.fieldname for f in meta.fields]
        self.assertIn("article", field_names)
        self.assertIn("damage_description", field_names)
        self.assertIn("estimated_replacement_cost_sar", field_names)
        self.assertTrue(len(field_names) > 0)
