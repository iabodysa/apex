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


class TestCustodyReturn(FrappeTestCase):

    def test_create_valid_return(self):
        doc = frappe.get_doc({
            "doctype": "Custody Return",
            "naming_series": "CUST-RET-.YYYY.-.####",
            "return_date": "2026-07-01",
            "custody_issue": "CUST-ISS-QA",
            "items": [{"doctype": "Custody Return Item", "article": "QA-ART", "qty": 1}],
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.assertIsNotNone(doc.name)
        frappe.delete_doc("Custody Return", doc.name, force=True, ignore_permissions=True)

    def test_missing_return_date_raises(self):
        doc = frappe.get_doc({
            "doctype": "Custody Return",
            "naming_series": "CUST-RET-.YYYY.-.####",
            "custody_issue": "CUST-ISS-QA",
        })
        with self.assertRaises(frappe.exceptions.ValidationError):
            doc.insert(ignore_permissions=True, ignore_links=True)

    def test_empty_items_raises(self):
        from apex_habitat.habitat.doctype.custody_return.custody_return import validate

        doc = frappe.get_doc({
            "doctype": "Custody Return",
            "return_date": "2026-07-01",
            "custody_issue": "CUST-ISS-QA",
            "items": [],
        })
        with self.assertRaises(frappe.ValidationError):
            validate(doc)

    # --- per-article return progress (bug #1) -------------------------------
    # A Custody Issue is "Returned" only when EVERY issued article is fully
    # accounted for — never from a cross-article quantity SUM.
    def test_progress_partial_when_one_article_short(self):
        from apex_habitat.habitat.doctype.custody_return.custody_return import _progress_from
        self.assertEqual(_progress_from({"A": 5}, {"A": 3}), "Partially Returned")

    def test_progress_multi_article_full_only_when_all_complete(self):
        from apex_habitat.habitat.doctype.custody_return.custody_return import _progress_from
        # A fully returned but B untouched: 5/10 by SUM, but per-article incomplete.
        self.assertEqual(_progress_from({"A": 5, "B": 5}, {"A": 5}), "Partially Returned")
        self.assertEqual(_progress_from({"A": 5, "B": 5}, {"A": 5, "B": 5}), "Returned")

    def test_progress_returned_when_each_article_met(self):
        from apex_habitat.habitat.doctype.custody_return.custody_return import _progress_from
        self.assertEqual(_progress_from({"A": 5}, {"A": 5}), "Returned")

    def test_progress_issued_when_nothing_returned(self):
        from apex_habitat.habitat.doctype.custody_return.custody_return import _progress_from
        self.assertEqual(_progress_from({"A": 5}, {}), "Issued")
