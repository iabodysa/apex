import frappe
import unittest
from frappe.tests.utils import FrappeTestCase


class TestSubcontractorServiceContract(FrappeTestCase):

    def test_create_valid_contract(self):
        doc = frappe.get_doc({
            "doctype": "Subcontractor Service Contract",
            "naming_series": "SUB-CON-.YYYY.-.####",
            "supplier": "QA-SUPPLIER",
            "service_type": "Pest Control",
            "contract_start_date": "2026-01-01",
            "contract_end_date": "2026-12-31",
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.assertEqual(doc.service_type, "Pest Control")
        frappe.delete_doc("Subcontractor Service Contract", doc.name, force=True, ignore_permissions=True)

    def test_missing_supplier_raises(self):
        doc = frappe.get_doc({
            "doctype": "Subcontractor Service Contract",
            "naming_series": "SUB-CON-.YYYY.-.####",
            "service_type": "Deep Cleaning",
            "contract_start_date": "2026-01-01",
            "contract_end_date": "2026-12-31",
        })
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert(ignore_permissions=True, ignore_links=True)

    def test_missing_end_date_raises(self):
        doc = frappe.get_doc({
            "doctype": "Subcontractor Service Contract",
            "naming_series": "SUB-CON-.YYYY.-.####",
            "supplier": "QA-SUPPLIER",
            "service_type": "AC Maintenance",
            "contract_start_date": "2026-01-01",
        })
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert(ignore_permissions=True, ignore_links=True)
