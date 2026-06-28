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


class TestCustodyReturnDamageAssessment(FrappeTestCase):
    """The 'Create Damage Assessment' action maps only Damaged/Lost rows from a
    return into a pre-filled draft assessment that back-links the return."""

    def setUp(self):
        h = frappe.generate_hash(length=4).upper()
        self.cat = frappe.get_doc({
            "doctype": "Custody Asset Category", "category_name": "Cat " + h,
        }).insert(ignore_permissions=True).name
        self.damaged_article = frappe.get_doc({
            "doctype": "Custody Article", "naming_series": "ART-.####",
            "article_name": "Damaged " + h, "category": self.cat,
        }).insert(ignore_permissions=True).name
        self.good_article = frappe.get_doc({
            "doctype": "Custody Article", "naming_series": "ART-.####",
            "article_name": "Good " + h, "category": self.cat,
        }).insert(ignore_permissions=True).name

    def _return(self, conditions):
        """A saved Custody Return with one row per (article, condition_on_return).
        Links are placeholder strings (ignore_links) — the mapper reads by name and
        never re-validates the source's links."""
        doc = frappe.get_doc({
            "doctype": "Custody Return",
            "naming_series": "CUST-RET-.YYYY.-.####",
            "return_date": "2026-07-01",
            "custody_issue": "CUST-ISS-QA",
            "building": "QA-BLDG",
            "party_type": "Temporary Worker",
            "party": "QA-TW",
            "items": [
                {"doctype": "Custody Return Item", "article": art, "qty": 1,
                 "condition_on_return": cond}
                for art, cond in conditions
            ],
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.addCleanup(frappe.delete_doc, "Custody Return", doc.name,
                        force=True, ignore_permissions=True)
        return doc

    def test_maps_only_damaged_and_lost_rows(self):
        from apex_habitat.habitat.doctype.custody_return.custody_return import (
            make_damage_assessment,
        )
        ret = self._return([
            (self.good_article, "Good"),
            (self.damaged_article, "Damaged"),
        ])
        target = make_damage_assessment(ret.name)
        self.assertEqual(target.doctype, "Custody Damage Assessment")
        self.assertEqual(target.custody_return, ret.name)
        self.assertEqual(target.building, "QA-BLDG")
        self.assertEqual(target.party_type, "Temporary Worker")
        self.assertEqual(target.party, "QA-TW")
        self.assertTrue(target.assessment_date)
        self.assertEqual(len(target.items), 1)
        self.assertEqual(target.items[0].article, self.damaged_article)

    def test_lost_condition_also_carries_over(self):
        from apex_habitat.habitat.doctype.custody_return.custody_return import (
            make_damage_assessment,
        )
        ret = self._return([(self.damaged_article, "Lost")])
        target = make_damage_assessment(ret.name)
        self.assertEqual(len(target.items), 1)
        self.assertEqual(target.items[0].article, self.damaged_article)

    def test_no_damaged_rows_maps_no_items(self):
        from apex_habitat.habitat.doctype.custody_return.custody_return import (
            make_damage_assessment,
        )
        ret = self._return([(self.good_article, "Good")])
        target = make_damage_assessment(ret.name)
        self.assertEqual(len(target.items), 0)

    def test_button_gated_on_docstatus_and_damaged_condition(self):
        """The client button only appears for a submitted return that has a
        Damaged/Lost row."""
        import pathlib
        js = pathlib.Path(__file__).with_name("custody_return.js").read_text()
        self.assertIn("frm.doc.docstatus === 1", js)
        self.assertIn("Damaged", js)
        self.assertIn("Lost", js)
        self.assertIn("make_damage_assessment", js)


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
