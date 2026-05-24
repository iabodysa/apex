import frappe
from frappe.tests.utils import FrappeTestCase


class TestHabitatSettings(FrappeTestCase):

    def test_single_doctype_loads(self):
        doc = frappe.get_single("Habitat Settings")
        self.assertEqual(doc.doctype, "Habitat Settings")

    def test_custody_integration_mode_field_exists(self):
        meta = frappe.get_meta("Habitat Settings")
        field_names = [f.fieldname for f in meta.fields]
        self.assertIn("custody_integration_mode", field_names)

    def test_set_custody_mode_in_memory(self):
        doc = frappe.get_single("Habitat Settings")
        doc.custody_integration_mode = "Habitat Internal / No Financial Posting"
        self.assertEqual(doc.custody_integration_mode, "Habitat Internal / No Financial Posting")
