import frappe
import unittest
from frappe.tests.utils import FrappeTestCase


class TestLinkedMaintenanceRequestItem(FrappeTestCase):

    def test_child_metadata(self):
        meta = frappe.get_meta("Linked Maintenance Request Item")
        self.assertEqual(meta.istable, 1)

    def test_row_in_memory(self):
        row = frappe.new_doc("Linked Maintenance Request Item")
        row.issue_type = "Plumbing"
        self.assertEqual(row.doctype, "Linked Maintenance Request Item")

    def test_required_fields_defined(self):
        meta = frappe.get_meta("Linked Maintenance Request Item")
        field_names = [f.fieldname for f in meta.fields]
        self.assertTrue(len(field_names) > 0)
