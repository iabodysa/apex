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


class TestScheduledTaskInstance(FrappeTestCase):

    def test_create_valid_instance(self):
        doc = frappe.get_doc({
            "doctype": "Scheduled Task Instance",
            "naming_series": "STI-.YYYY.-.####",
            "template": "QA TEMPLATE",
            "due_date": "2026-06-25",
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.assertIsNotNone(doc.name)
        frappe.delete_doc("Scheduled Task Instance", doc.name, force=True, ignore_permissions=True)

    def test_missing_template_raises(self):
        doc = frappe.get_doc({
            "doctype": "Scheduled Task Instance",
            "naming_series": "STI-.YYYY.-.####",
            "due_date": "2026-06-25",
        })
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert(ignore_permissions=True, ignore_links=True)

    def test_missing_due_date_raises(self):
        from apex_habitat.habitat.doctype.scheduled_task_instance.scheduled_task_instance import validate

        doc = frappe.get_doc({
            "doctype": "Scheduled Task Instance",
            "template": "QA TEMPLATE",
            "due_date": None,
        })
        with self.assertRaises(frappe.ValidationError):
            validate(doc)
