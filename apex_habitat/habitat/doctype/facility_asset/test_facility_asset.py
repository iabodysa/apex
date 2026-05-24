import frappe
from frappe.tests.utils import FrappeTestCase

# Prevent Frappe test runner from recursively resolving Link-field dependencies
# on external DocTypes that require ERPNext (not installed in CI bench).
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


class TestFacilityAsset(FrappeTestCase):

    def test_create_valid_asset(self):
        doc = frappe.get_doc({
            "doctype": "Facility Asset",
            "naming_series": "FAC-AST-.YYYY.-.####",
            "asset_name": "QA CCTV Camera 1",
            "asset_category": "CCTV Camera",
            "building": "QA-BLDG",
            "responsible_supervisor": "Administrator",
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.assertEqual(doc.asset_name, "QA CCTV Camera 1")
        frappe.delete_doc("Facility Asset", doc.name, force=True, ignore_permissions=True)

    def test_missing_asset_name_raises(self):
        doc = frappe.get_doc({
            "doctype": "Facility Asset",
            "naming_series": "FAC-AST-.YYYY.-.####",
            "asset_category": "CCTV Camera",
            "building": "QA-BLDG",
            "responsible_supervisor": "Administrator",
        })
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert(ignore_permissions=True, ignore_links=True)

    def test_missing_building_raises(self):
        doc = frappe.get_doc({
            "doctype": "Facility Asset",
            "naming_series": "FAC-AST-.YYYY.-.####",
            "asset_name": "QA Generator",
            "asset_category": "Generator",
            "responsible_supervisor": "Administrator",
        })
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert(ignore_permissions=True, ignore_links=True)
