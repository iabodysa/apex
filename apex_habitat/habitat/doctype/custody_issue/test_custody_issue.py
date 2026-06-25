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


class TestCustodyIssueSerializedRules(FrappeTestCase):
    """A serialized article must carry a serial_no and qty==1 on every line."""

    def setUp(self):
        h = frappe.generate_hash(length=4).upper()
        cat = frappe.db.get_value("Custody Asset Category", {}) or frappe.get_doc({
            "doctype": "Custody Asset Category", "category_name": "Cat " + h,
        }).insert(ignore_permissions=True).name
        self.article = frappe.get_doc({
            "doctype": "Custody Article", "naming_series": "ART-.####",
            "article_name": "Serial " + h, "category": cat, "is_serialized": 1,
        }).insert(ignore_permissions=True).name

    def _issue(self, qty, serial_no):
        return frappe.get_doc({
            "doctype": "Custody Issue", "issue_date": "2026-06-01", "building": "QA-BLDG",
            "items": [{"doctype": "Custody Issue Item", "article": self.article,
                       "qty": qty, "serial_no": serial_no}],
        })

    def test_serialized_requires_serial_no(self):
        from apex_habitat.habitat.doctype.custody_issue.custody_issue import validate
        with self.assertRaises(frappe.ValidationError):
            validate(self._issue(qty=1, serial_no=""))

    def test_serialized_requires_qty_one(self):
        from apex_habitat.habitat.doctype.custody_issue.custody_issue import validate
        with self.assertRaises(frappe.ValidationError):
            validate(self._issue(qty=2, serial_no="SN-1"))

    def test_serialized_passes_with_serial_and_qty_one(self):
        from apex_habitat.habitat.doctype.custody_issue.custody_issue import validate
        validate(self._issue(qty=1, serial_no="SN-1"))


ACK_NOTIFICATION = "Habitat - Custody Acknowledgment Requested"


class TestCustodyAcknowledgmentNotification(FrappeTestCase):
    """The submit-time alert that makes the My Custody Acknowledgment Web Form
    reachable to the holder without the raw URL."""

    def test_notification_targets_holder_on_submit(self):
        n = frappe.get_doc("Notification", ACK_NOTIFICATION)
        self.assertEqual(n.document_type, "Custody Issue")
        self.assertEqual(n.event, "Submit")
        fields = [r.receiver_by_document_field for r in n.recipients]
        # Recipient resolves to a real email via the user mirror, not the Employee docname.
        self.assertIn("issued_to_user", fields)

    def test_message_renders_acknowledgment_form_link(self):
        n = frappe.get_doc("Notification", ACK_NOTIFICATION)
        rendered = frappe.render_template(n.message, {"doc": frappe._dict(name="CUST-ISS-QA")})
        self.assertIn("/my-custody-acknowledgment", rendered)
        # the holder lands pre-filtered to their own issue
        self.assertIn("custody_issue=CUST-ISS-QA", rendered)
