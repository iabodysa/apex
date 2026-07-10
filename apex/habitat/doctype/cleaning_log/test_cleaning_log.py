# Copyright (c) 2026, AFMCO and contributors
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


class TestCleaningLog(FrappeTestCase):

    def test_docperm_cleaning_supervisor(self):
        """Cleaning Supervisor must have read/write/create on Cleaning Log."""
        meta = frappe.get_meta("Cleaning Log")
        roles = {p.role: p for p in meta.permissions}
        self.assertIn("Cleaning Supervisor", roles, "Cleaning Supervisor perm row is missing")
        p = roles["Cleaning Supervisor"]
        self.assertEqual(p.read, 1)
        self.assertEqual(p.write, 1)
        self.assertEqual(p.create, 1)

    def test_create_valid_cleaning_log(self):
        doc = frappe.get_doc({
            "doctype": "Cleaning Log",
            "naming_series": "CLEAN-.YYYY.-.####",
            "building": "QA-BLDG",
            "cleaning_date": "2026-06-15",
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.assertEqual(doc.cleaning_date, "2026-06-15")
        frappe.delete_doc("Cleaning Log", doc.name, force=True, ignore_permissions=True)

    def test_missing_building_raises(self):
        doc = frappe.get_doc({
            "doctype": "Cleaning Log",
            "naming_series": "CLEAN-.YYYY.-.####",
            "cleaning_date": "2026-06-15",
        })
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert(ignore_permissions=True, ignore_links=True)

    def test_missing_cleaning_date_raises(self):
        doc = frappe.get_doc({
            "doctype": "Cleaning Log",
            "naming_series": "CLEAN-.YYYY.-.####",
            "building": "QA-BLDG",
        })
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert(ignore_permissions=True, ignore_links=True)

    def test_submit_without_required_area_evidence_raises(self):
        """The forbidden action: submit with no area photo evidence must fail."""
        doc = frappe.get_doc({
            "doctype": "Cleaning Log",
            "naming_series": "CLEAN-.YYYY.-.####",
            "building": "QA-BLDG",
            "cleaning_date": "2026-06-15",
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        with self.assertRaises(frappe.exceptions.ValidationError):
            doc.submit()
        frappe.delete_doc("Cleaning Log", doc.name, force=True, ignore_permissions=True)

    def test_submit_with_all_required_areas_passes(self):
        """A Cleaned photo or an excused (N/A + note) row satisfies each area."""
        doc = frappe.get_doc({
            "doctype": "Cleaning Log",
            "naming_series": "CLEAN-.YYYY.-.####",
            "building": "QA-BLDG",
            "cleaning_date": "2026-06-15",
            "area_photos": [
                {"area": "Bathrooms", "status": "Cleaned", "photo": "/files/qa-bath.jpg"},
                {"area": "Kitchen", "status": "Cleaned", "photo": "/files/qa-kitchen.jpg"},
                {"area": "Corridors", "status": "N/A", "note": "No corridor in this unit"},
            ],
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        doc.submit()
        self.assertEqual(doc.docstatus, 1)
        # captured_at is server-stamped on the photo rows, never client-supplied.
        photo_rows = [r for r in doc.area_photos if r.photo]
        self.assertTrue(all(r.captured_at for r in photo_rows))
        doc.cancel()
        frappe.delete_doc("Cleaning Log", doc.name, force=True, ignore_permissions=True)

    def test_submit_cleaned_area_without_photo_raises(self):
        """A required area marked Cleaned but with no photo must fail the gate."""
        doc = frappe.get_doc({
            "doctype": "Cleaning Log",
            "naming_series": "CLEAN-.YYYY.-.####",
            "building": "QA-BLDG",
            "cleaning_date": "2026-06-15",
            "area_photos": [
                {"area": "Bathrooms", "status": "Cleaned"},
                {"area": "Kitchen", "status": "Cleaned", "photo": "/files/qa-kitchen.jpg"},
                {"area": "Corridors", "status": "Cleaned", "photo": "/files/qa-corridor.jpg"},
            ],
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        with self.assertRaises(frappe.exceptions.ValidationError):
            doc.submit()
        frappe.delete_doc("Cleaning Log", doc.name, force=True, ignore_permissions=True)
