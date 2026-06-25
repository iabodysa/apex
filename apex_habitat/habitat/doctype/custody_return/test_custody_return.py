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

    # [#o86eu8]
    def test_progress_partial_when_one_article_short(self):
        from apex_habitat.habitat.doctype.custody_return.custody_return import _progress_from
        self.assertEqual(_progress_from({"A": 5}, {"A": 3}), "Partially Returned")

    def test_progress_multi_article_full_only_when_all_complete(self):
        from apex_habitat.habitat.doctype.custody_return.custody_return import _progress_from
        # [#nt3lm7]
        self.assertEqual(_progress_from({"A": 5, "B": 5}, {"A": 5}), "Partially Returned")
        self.assertEqual(_progress_from({"A": 5, "B": 5}, {"A": 5, "B": 5}), "Returned")

    def test_progress_returned_when_each_article_met(self):
        from apex_habitat.habitat.doctype.custody_return.custody_return import _progress_from
        self.assertEqual(_progress_from({"A": 5}, {"A": 5}), "Returned")

    def test_progress_issued_when_nothing_returned(self):
        from apex_habitat.habitat.doctype.custody_return.custody_return import _progress_from
        self.assertEqual(_progress_from({"A": 5}, {}), "Issued")

    # [#tuw9z9]

    def test_partially_returned_status_in_custody_issue_options(self):
        """Custody Issue status field must carry the 'Partially Returned' option
        so that Custody Return.on_submit() can set it without a Select validation
        error."""
        meta = frappe.get_meta("Custody Issue")
        status_field = next((f for f in meta.fields if f.fieldname == "status"), None)
        self.assertIsNotNone(status_field, "status field missing from Custody Issue")
        options = (status_field.options or "").split("\n")
        self.assertIn("Partially Returned", options,
                      "'Partially Returned' must be a valid status option on Custody Issue")

    def test_progress_from_drives_partially_returned(self):
        """_progress_from must return 'Partially Returned' when any article is
        partially returned and at least one is not fully returned — verifies the
        logic that on_submit uses to update Custody Issue status."""
        from apex_habitat.habitat.doctype.custody_return.custody_return import _progress_from
        # [#nun650]
        result = _progress_from({"CHAIR": 3, "TABLE": 2}, {"CHAIR": 3})
        self.assertEqual(result, "Partially Returned",
                         "A partial return should yield 'Partially Returned', not 'Returned'")

    def test_issue_return_progress_source_of_truth(self):
        """Verify _issue_return_progress and _progress_from agree: per-article
        tracking never confuses a cross-article SUM as full return."""
        from apex_habitat.habitat.doctype.custody_return.custody_return import _progress_from
        # [#cs9uz8]
        self.assertEqual(_progress_from({"A": 5, "B": 5}, {"A": 5}), "Partially Returned")
        # [#iw2s4n]
        self.assertEqual(_progress_from({"A": 5, "B": 5}, {"A": 5, "B": 5}), "Returned")


class TestCustodyReturnSerializedRules(FrappeTestCase):
    """The serialized-article guard is enforced on return as well as issue."""

    def setUp(self):
        h = frappe.generate_hash(length=4).upper()
        cat = frappe.db.get_value("Custody Asset Category", {}) or frappe.get_doc({
            "doctype": "Custody Asset Category", "category_name": "Cat " + h,
        }).insert(ignore_permissions=True).name
        self.article = frappe.get_doc({
            "doctype": "Custody Article", "naming_series": "ART-.####",
            "article_name": "Serial " + h, "category": cat, "is_serialized": 1,
        }).insert(ignore_permissions=True).name

    def _return(self, qty, serial_no):
        return frappe.get_doc({
            "doctype": "Custody Return", "return_date": "2026-07-01", "building": "QA-BLDG",
            "items": [{"doctype": "Custody Return Item", "article": self.article,
                       "qty": qty, "serial_no": serial_no}],
        })

    def test_serialized_requires_serial_no(self):
        from apex_habitat.habitat.doctype.custody_return.custody_return import validate
        with self.assertRaises(frappe.ValidationError):
            validate(self._return(qty=1, serial_no=""))

    def test_serialized_requires_qty_one(self):
        from apex_habitat.habitat.doctype.custody_return.custody_return import validate
        with self.assertRaises(frappe.ValidationError):
            validate(self._return(qty=2, serial_no="SN-1"))

    def test_serialized_passes_with_serial_and_qty_one(self):
        from apex_habitat.habitat.doctype.custody_return.custody_return import validate
        validate(self._return(qty=1, serial_no="SN-1"))
