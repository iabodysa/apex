import frappe
from frappe.tests.utils import FrappeTestCase

# [#8evoal]
test_ignore = [
    "Additional Salary",
    "Asset",
    "Asset Movement",
    "Company",
    "Cost Center",
    "Currency",
    "Employee",
    "Item",
    "Payment Entry",
    "Project",
    "Purchase Invoice",
    "Role",
    "Salary Component",
    "Supplier",
    "User",
]



class TestAccommodationLease(FrappeTestCase):

    def test_create_valid_lease(self):
        doc = frappe.get_doc({
            "doctype": "Accommodation Lease",
            "naming_series": "ACC-LEASE-.YYYY.-.####",
            "building": "QA-BLDG",
            "lease_start_date": "2026-01-01",
            "lease_end_date": "2026-12-31",
            "rent_amount": 8000,
            "first_payment_date": "2026-01-01",
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
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

    def test_schedule_rows_default_unpaid(self):
        """Generated schedule rows are stamped 'Unpaid', never 'Paid'. The
        'Generate Payment' button selects the next non-Paid row, so a fresh row
        must read Unpaid for that selection to land on it (guards the row-pick
        contract the form button depends on)."""
        from apex_habitat.habitat.doctype.accommodation_lease.accommodation_lease import _build_schedule

        doc = frappe.get_doc({
            "doctype": "Accommodation Lease",
            "naming_series": "ACC-LEASE-.YYYY.-.####",
            "building": "QA-BLDG",
            "lease_start_date": "2026-01-01",
            "lease_end_date": "2026-06-30",
            "rent_amount": 4000,
            "first_payment_date": "2026-01-01",
            "billing_cycle": "Monthly",
        })
        _build_schedule(doc)
        self.assertTrue(doc.payment_schedule)
        self.assertTrue(all(r.status == "Unpaid" for r in doc.payment_schedule))
