import frappe
from frappe.tests.utils import FrappeTestCase



class TestAccommodationLease(FrappeTestCase):

    def test_create_valid_lease(self):
        doc = frappe.get_doc({
            "doctype": "Accommodation Lease",
            "naming_series": "ACC-LEASE-.YYYY.-.####",
            "building": "QA-BLDG",
            "lease_start_date": "2026-01-01",
            "lease_end_date": "2026-12-31",
            "rent_amount": 8000,
        })
        doc.insert(ignore_permissions=True)
        self.assertEqual(doc.rent_amount, 8000)
        frappe.delete_doc("Accommodation Lease", doc.name, force=True, ignore_permissions=True)

    def test_missing_building_raises(self):
        doc = frappe.get_doc({
            "doctype": "Accommodation Lease",
            "naming_series": "ACC-LEASE-.YYYY.-.####",
            "lease_start_date": "2026-01-01",
            "lease_end_date": "2026-12-31",
            "rent_amount": 5000,
        })
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert(ignore_permissions=True, ignore_links=True)

    def test_end_date_before_start_date_raises(self):
        from apex_habitat.habitat.doctype.accommodation_lease.accommodation_lease import validate
        doc = frappe.get_doc({
            "doctype": "Accommodation Lease",
            "building": "QA-BLDG",
            "lease_start_date": "2026-06-01",
            "lease_end_date": "2026-05-01",
            "rent_amount": 5000,
        })
        with self.assertRaises(frappe.ValidationError):
            validate(doc)
