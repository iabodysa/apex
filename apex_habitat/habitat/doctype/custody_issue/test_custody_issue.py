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


class TestCustodyIssue(FrappeTestCase):

    def test_create_valid_issue(self):
        doc = frappe.get_doc({
            "doctype": "Custody Issue",
            "naming_series": "CUST-ISS-.YYYY.-.####",
            "issue_date": "2026-06-01",
            "building": "QA-BLDG",
            "items": [{"doctype": "Custody Issue Item", "article": "QA-ART", "qty": 1}],
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.assertIsNotNone(doc.name)
        frappe.delete_doc("Custody Issue", doc.name, force=True, ignore_permissions=True)

    def test_missing_issue_date_raises(self):
        doc = frappe.get_doc({
            "doctype": "Custody Issue",
            "naming_series": "CUST-ISS-.YYYY.-.####",
            "building": "QA-BLDG",
        })
        with self.assertRaises(frappe.exceptions.ValidationError):
            doc.insert(ignore_permissions=True, ignore_links=True)

    def test_empty_items_raises(self):
        from apex_habitat.habitat.doctype.custody_issue.custody_issue import validate

        doc = frappe.get_doc({
            "doctype": "Custody Issue",
            "issue_date": "2026-06-01",
            "building": "QA-BLDG",
            "items": [],
        })
        with self.assertRaises(frappe.ValidationError):
            validate(doc)


ACK_NOTIFICATION = "Habitat - Custody Acknowledgment Requested"


class TestCustodyAcknowledgmentNotification(FrappeTestCase):
    """The submit-time alert that makes the My Custody Acknowledgment Web Form
    reachable to the holder without the raw URL."""

    def test_notification_targets_holder_on_submit(self):
        n = frappe.get_doc("Notification", ACK_NOTIFICATION)
        self.assertEqual(n.document_type, "Custody Issue")
        self.assertEqual(n.event, "Submit")
        fields = [r.receiver_by_document_field for r in n.recipients]
        self.assertIn("issued_to_employee", fields)

    def test_message_renders_acknowledgment_form_link(self):
        n = frappe.get_doc("Notification", ACK_NOTIFICATION)
        rendered = frappe.render_template(n.message, {"doc": frappe._dict(name="CUST-ISS-QA")})
        self.assertIn("/my-custody-acknowledgment", rendered)
        # the holder lands pre-filtered to their own issue
        self.assertIn("custody_issue=CUST-ISS-QA", rendered)
