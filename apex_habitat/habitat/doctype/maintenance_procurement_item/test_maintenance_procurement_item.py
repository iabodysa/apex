import frappe
import unittest
from frappe.tests.utils import FrappeTestCase


class TestMaintenanceProcurementItem(FrappeTestCase):

    def test_child_metadata(self):
        meta = frappe.get_meta("Maintenance Procurement Item")
        self.assertEqual(meta.istable, 1)

    def test_row_in_memory(self):
        row = frappe.new_doc("Maintenance Procurement Item")
        row.item_description = "bolt"
        row.quantity = 4
        self.assertEqual(row.doctype, "Maintenance Procurement Item")

    def test_required_fields_defined(self):
        meta = frappe.get_meta("Maintenance Procurement Item")
        field_names = [f.fieldname for f in meta.fields]
        self.assertTrue(len(field_names) > 0)
