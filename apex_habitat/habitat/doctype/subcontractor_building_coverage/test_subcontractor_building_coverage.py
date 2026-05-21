import frappe
import unittest
from frappe.tests.utils import FrappeTestCase


class TestSubcontractorBuildingCoverage(FrappeTestCase):

    def test_child_metadata(self):
        meta = frappe.get_meta("Subcontractor Building Coverage")
        self.assertEqual(meta.istable, 1)

    def test_row_in_memory(self):
        row = frappe.new_doc("Subcontractor Building Coverage")
        row.building = "test-bldg"
        self.assertEqual(row.doctype, "Subcontractor Building Coverage")

    def test_required_fields_defined(self):
        meta = frappe.get_meta("Subcontractor Building Coverage")
        field_names = [f.fieldname for f in meta.fields]
        self.assertIn("building", field_names)
        self.assertTrue(len(field_names) > 0)
