import frappe
import unittest
from frappe.tests.utils import FrappeTestCase


class TestSafetyInspectionFindingItem(FrappeTestCase):

    def test_child_metadata(self):
        meta = frappe.get_meta("Safety Inspection Finding Item")
        self.assertEqual(meta.istable, 1)

    def test_row_in_memory(self):
        row = frappe.new_doc("Safety Inspection Finding Item")
        row.severity = "High"
        row.location_description = "corridor"
        self.assertEqual(row.doctype, "Safety Inspection Finding Item")

    def test_required_fields_defined(self):
        meta = frappe.get_meta("Safety Inspection Finding Item")
        field_names = [f.fieldname for f in meta.fields]
        self.assertTrue(len(field_names) > 0)
