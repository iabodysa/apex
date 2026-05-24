import frappe
from frappe.tests.utils import FrappeTestCase


class TestRentPaymentSchedule(FrappeTestCase):

    def test_child_metadata(self):
        meta = frappe.get_meta("Rent Payment Schedule")
        self.assertEqual(meta.istable, 1)

    def test_row_in_memory(self):
        row = frappe.new_doc("Rent Payment Schedule")
        row.due_date = "2026-07-01"
        row.amount = 5000
        row.status = "Unpaid"
        self.assertEqual(row.doctype, "Rent Payment Schedule")

    def test_required_fields_defined(self):
        meta = frappe.get_meta("Rent Payment Schedule")
        field_names = [f.fieldname for f in meta.fields]
        self.assertIn("due_date", field_names)
        self.assertIn("amount", field_names)
        self.assertIn("status", field_names)
        self.assertTrue(len(field_names) > 0)
