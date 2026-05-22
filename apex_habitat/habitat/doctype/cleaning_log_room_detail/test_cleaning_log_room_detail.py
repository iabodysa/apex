import frappe
import unittest
from frappe.tests.utils import FrappeTestCase


class TestCleaningLogRoomDetail(FrappeTestCase):

    def test_child_metadata(self):
        meta = frappe.get_meta("Cleaning Log Room Detail")
        self.assertEqual(meta.istable, 1)

    def test_row_in_memory(self):
        row = frappe.new_doc("Cleaning Log Room Detail")
        row.room = "test-room"
        self.assertEqual(row.doctype, "Cleaning Log Room Detail")

    def test_required_fields_defined(self):
        meta = frappe.get_meta("Cleaning Log Room Detail")
        field_names = [f.fieldname for f in meta.fields]
        self.assertIn("room", field_names)
        self.assertTrue(len(field_names) > 0)
