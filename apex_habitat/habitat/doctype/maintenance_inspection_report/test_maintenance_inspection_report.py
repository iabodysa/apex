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


class TestMaintenanceInspectionReport(FrappeTestCase):

    def test_create_valid_report(self):
        doc = frappe.get_doc({
            "doctype": "Maintenance Inspection Report",
            "naming_series": "MIR-.YYYY.-.####",
            "inspection_date": "2026-06-20",
            "building": "QA-BLDG",
            "inspector": "EMP-QA-001",
            "findings": [{"doctype": "Inspection Finding Item", "description": "crack in wall"}],
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.assertIsNotNone(doc.name)
        frappe.delete_doc("Maintenance Inspection Report", doc.name, force=True, ignore_permissions=True)

    def test_missing_inspector_raises(self):
        doc = frappe.get_doc({
            "doctype": "Maintenance Inspection Report",
            "naming_series": "MIR-.YYYY.-.####",
            "inspection_date": "2026-06-20",
            "building": "QA-BLDG",
            "findings": [{"doctype": "Inspection Finding Item", "description": "crack in wall"}],
        })
        with self.assertRaises(frappe.exceptions.ValidationError):
            doc.insert(ignore_permissions=True, ignore_links=True)

    def test_empty_findings_raises(self):
        from apex_habitat.habitat.doctype.maintenance_inspection_report.maintenance_inspection_report import validate

        doc = frappe.get_doc({
            "doctype": "Maintenance Inspection Report",
            "inspection_date": "2026-06-20",
            "building": "QA-BLDG",
            "inspector": "EMP-QA-001",
            "findings": [],
        })
        with self.assertRaises(frappe.ValidationError):
            validate(doc)
