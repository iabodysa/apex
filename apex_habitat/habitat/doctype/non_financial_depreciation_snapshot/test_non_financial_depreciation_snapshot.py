import frappe
import unittest
from frappe.tests.utils import FrappeTestCase


class TestNonFinancialDepreciationSnapshot(FrappeTestCase):

    def test_create_valid_snapshot(self):
        doc = frappe.get_doc({
            "doctype": "Non-Financial Depreciation Snapshot",
            "naming_series": "DEP-SNAP-.YYYY.-.####",
            "snapshot_date": "2026-06-30",
            "building": "QA-BLDG",
            "items": [{"doctype": "Depreciation Snapshot Item",
                        "article": "QA-ART", "original_cost_sar": 200}],
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.assertIsNotNone(doc.name)
        frappe.delete_doc("Non-Financial Depreciation Snapshot", doc.name, force=True, ignore_permissions=True)

    def test_missing_snapshot_date_raises(self):
        doc = frappe.get_doc({
            "doctype": "Non-Financial Depreciation Snapshot",
            "naming_series": "DEP-SNAP-.YYYY.-.####",
            "building": "QA-BLDG",
        })
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert(ignore_permissions=True, ignore_links=True)

    def test_empty_items_raises(self):
        from apex_habitat.habitat.doctype.non_financial_depreciation_snapshot.non_financial_depreciation_snapshot import validate
        doc = frappe.get_doc({
            "doctype": "Non-Financial Depreciation Snapshot",
            "snapshot_date": "2026-06-30",
            "building": "QA-BLDG",
            "items": [],
        })
        with self.assertRaises(frappe.ValidationError):
            validate(doc)
