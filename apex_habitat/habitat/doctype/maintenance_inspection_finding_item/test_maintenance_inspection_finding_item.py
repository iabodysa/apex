import frappe
from frappe.tests.utils import FrappeTestCase


class TestMaintenanceInspectionFindingItem(FrappeTestCase):

    def test_child_metadata(self):
        meta = frappe.get_meta("Maintenance Inspection Finding Item")
        self.assertEqual(meta.istable, 1)

    def test_row_in_memory(self):
        row = frappe.new_doc("Maintenance Inspection Finding Item")
        row.description = "pipe leak"
        self.assertEqual(row.doctype, "Maintenance Inspection Finding Item")

    def test_required_fields_defined(self):
        meta = frappe.get_meta("Maintenance Inspection Finding Item")
        field_names = [f.fieldname for f in meta.fields]
        self.assertIn("description", field_names)
        self.assertTrue(len(field_names) > 0)
