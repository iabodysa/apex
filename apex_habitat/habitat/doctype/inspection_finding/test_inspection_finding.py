import frappe
from frappe.tests.utils import FrappeTestCase


class TestInspectionFinding(FrappeTestCase):

    def test_child_metadata(self):
        meta = frappe.get_meta("Inspection Finding")
        self.assertEqual(meta.istable, 1)

    def test_row_in_memory(self):
        row = frappe.new_doc("Inspection Finding")
        row.finding_description = "crack in wall"
        self.assertEqual(row.doctype, "Inspection Finding")

    def test_required_fields_defined(self):
        meta = frappe.get_meta("Inspection Finding")
        field_names = [f.fieldname for f in meta.fields]
        self.assertIn("finding_description", field_names)
        self.assertTrue(len(field_names) > 0)
