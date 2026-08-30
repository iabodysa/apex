# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

test_dependencies = ["Building", "Operational Depreciation Policy"]


class TestOperationalDepreciationSnapshotBookValue(FrappeTestCase):
    def _snapshot(self, **fields):
        data = {
            "doctype": "Operational Depreciation Snapshot",
            "snapshot_date": "2026-01-31",
            "building": "_Test Building",
            "items": [
                {
                    "article": "_Test Blanket",
                    "policy": "_Test Straight Line 5yr",
                    "original_cost": 1000,
                    "age_years": 2,
                }
            ],
        }
        data.update(fields)
        doc = frappe.get_doc(data)
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.addCleanup(self._purge, doc.name)
        return doc

    @staticmethod
    def _purge(name):
        doc = frappe.get_doc("Operational Depreciation Snapshot", name)
        if doc.docstatus == 1:
            doc.cancellation_reason = "test teardown"
            doc.cancel()
        frappe.delete_doc(
            "Operational Depreciation Snapshot", name, ignore_permissions=True, force=True
        )

    def test_the_straight_line_formula_computes_the_rows_book_value_and_the_total(self):
        doc = self._snapshot()
        self.assertEqual(doc.items[0].book_value, 640)
        self.assertEqual(doc.total_book_value, 640)

    def test_cancelling_without_a_reason_is_refused(self):
        doc = self._snapshot()
        doc.submit()
        doc.cancellation_reason = None
        with self.assertRaises(frappe.ValidationError):
            doc.cancel()
