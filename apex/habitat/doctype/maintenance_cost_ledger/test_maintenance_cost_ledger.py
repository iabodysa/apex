# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

test_dependencies = ["Building"]
test_ignore = [
    "Item",
    "Maintenance Material",
    "Maintenance Work Order",
    "Maintenance Request",
]


class TestMaintenanceCostLedgerImmutability(FrappeTestCase):
    def _row(self, **fields):
        data = {
            "doctype": "Maintenance Cost Ledger",
            "posting_date": "2026-01-12",
            "building": "_Test Building",
            "item_description": "Plumbing repair parts",
            "amount": 250,
            "source_doctype": "Maintenance Work Order",
            "source_name": "_T-MWO-9001",
            "source_detail_no": 1,
        }
        data.update(fields)
        doc = frappe.get_doc(data)
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.addCleanup(
            lambda name=doc.name: frappe.db.delete(
                "Maintenance Cost Ledger", {"name": name}
            )
        )
        return doc

    def test_editing_a_posted_row_after_insert_is_refused(self):
        doc = self._row()
        doc.amount = 999
        with self.assertRaises(frappe.ValidationError):
            doc.save(ignore_permissions=True)
