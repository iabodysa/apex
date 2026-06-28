# Copyright (c) 2026, AFMCO and contributors
import frappe
from frappe.tests.utils import FrappeTestCase

test_ignore = [
    "Accommodation Building",
    "Custody Article",
    "Custody Issue",
    "Employee",
    "Role",
    "User",
]


class TestCustodyAcknowledgment(FrappeTestCase):

    def _make_submitted_issue(self):
        issue = frappe.get_doc({
            "doctype": "Custody Issue",
            "naming_series": "CUST-ISS-.YYYY.-.####",
            "issue_date": "2026-06-01",
            "building": "QA-BLDG",
            "items": [{"doctype": "Custody Issue Item", "article": "QA-ART", "qty": 1}],
        })
        issue.insert(ignore_permissions=True, ignore_links=True)
        issue.submit()
        return issue

    def test_confirmed_receipt_records_ack(self):
        issue = self._make_submitted_issue()
        ack = frappe.get_doc({
            "doctype": "Custody Acknowledgment",
            "custody_issue": issue.name,
            "confirmation_method": "Confirmed Receipt",
            "receipt_confirmed": 1,
        })
        ack.insert(ignore_permissions=True, ignore_links=True)
        self.assertIsNotNone(ack.name)
        self.assertIsNotNone(ack.acknowledged_on)
        frappe.delete_doc("Custody Acknowledgment", ack.name, force=True, ignore_permissions=True)
        issue.cancel()
        frappe.delete_doc("Custody Issue", issue.name, force=True, ignore_permissions=True)

    def test_signature_fallback_records_ack(self):
        issue = self._make_submitted_issue()
        ack = frappe.get_doc({
            "doctype": "Custody Acknowledgment",
            "custody_issue": issue.name,
            "confirmation_method": "Signature",
            "signature": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUg==",
        })
        ack.insert(ignore_permissions=True, ignore_links=True)
        self.assertIsNotNone(ack.name)
        frappe.delete_doc("Custody Acknowledgment", ack.name, force=True, ignore_permissions=True)
        issue.cancel()
        frappe.delete_doc("Custody Issue", issue.name, force=True, ignore_permissions=True)

    def test_unconfirmed_ack_raises(self):
        issue = self._make_submitted_issue()
        ack = frappe.get_doc({
            "doctype": "Custody Acknowledgment",
            "custody_issue": issue.name,
            "confirmation_method": "Confirmed Receipt",
            "receipt_confirmed": 0,
        })
        with self.assertRaises(frappe.ValidationError):
            ack.insert(ignore_permissions=True, ignore_links=True)
        issue.cancel()
        frappe.delete_doc("Custody Issue", issue.name, force=True, ignore_permissions=True)

    def test_web_form_route_renders_200(self):
        """The My Custody Acknowledgment Web Form route resolves and renders the
        form (HTTP 200 with its fields) for a logged-in holder."""
        from frappe.utils import set_request
        from frappe.website.serve import get_response

        self.assertTrue(
            frappe.db.exists("Web Form", "my-custody-acknowledgment"),
            "Web Form is not registered",
        )
        set_request(method="GET", path="/my-custody-acknowledgment/new")
        frappe.set_user("Administrator")
        try:
            resp = get_response("/my-custody-acknowledgment/new")
            body = resp.get_data(as_text=True)
        finally:
            frappe.set_user("Administrator")

        self.assertEqual(resp.status_code, 200)
        self.assertIn("My Custody Acknowledgment", body)
        self.assertIn("custody_issue", body)
        self.assertIn("signature", body)
