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
        from apex.habitat.doctype.scheduled_task_instance.scheduled_task_instance import validate

        doc = frappe.get_doc({
            "doctype": "Scheduled Task Instance",
            "template": "QA TEMPLATE",
            "due_date": None,
        })
        with self.assertRaises(frappe.ValidationError):
            validate(doc)

    def test_mark_completed_stamps_completed_date(self):
        """mark_completed() must set completed_date to today (P-080)."""
        from apex.habitat.doctype.scheduled_task_instance.scheduled_task_instance import mark_completed

        doc = frappe.get_doc({
            "doctype": "Scheduled Task Instance",
            "naming_series": "STI-.YYYY.-.####",
            "template": "QA TEMPLATE",
            "due_date": frappe.utils.today(),
            "status": "Open",
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        # Set docstatus=1 directly to satisfy mark_completed()'s guard without
        # running submit()'s link-validation (QA TEMPLATE is a stub name).
        frappe.db.set_value("Scheduled Task Instance", doc.name, "docstatus", 1)
        doc.reload()
        try:
            mark_completed(doc.name)
            doc.reload()
            self.assertEqual(doc.completed_date, frappe.utils.getdate())
        finally:
            frappe.db.set_value("Scheduled Task Instance", doc.name, "docstatus", 2)
            frappe.delete_doc("Scheduled Task Instance", doc.name, force=True, ignore_permissions=True)
