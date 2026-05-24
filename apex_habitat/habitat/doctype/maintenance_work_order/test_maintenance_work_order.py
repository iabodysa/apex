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


class TestMaintenanceWorkOrder(FrappeTestCase):

    def test_create_valid_work_order(self):
        doc = frappe.get_doc({
            "doctype": "Maintenance Work Order",
            "naming_series": "MWO-.YYYY.-.####",
            "maintenance_request": "MAINT-QA-001",
            "work_description": "Fix pipe leak in room 101",
            "planned_start_date": "2026-06-10",
            "planned_end_date": "2026-06-12",
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.assertIsNotNone(doc.name)
        frappe.delete_doc("Maintenance Work Order", doc.name, force=True, ignore_permissions=True)

    def test_missing_work_description_raises(self):
        doc = frappe.get_doc({
            "doctype": "Maintenance Work Order",
            "naming_series": "MWO-.YYYY.-.####",
            "maintenance_request": "MAINT-QA-001",
            "planned_start_date": "2026-06-10",
        })
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert(ignore_permissions=True, ignore_links=True)

    def test_end_date_before_start_raises(self):
        from apex_habitat.habitat.doctype.maintenance_work_order.maintenance_work_order import validate

        doc = frappe.get_doc({
            "doctype": "Maintenance Work Order",
            "maintenance_request": "MAINT-QA-001",
            "work_description": "Repair work",
            "planned_start_date": "2026-06-15",
            "planned_end_date": "2026-06-10",
        })
        with self.assertRaises(frappe.ValidationError):
            validate(doc)
