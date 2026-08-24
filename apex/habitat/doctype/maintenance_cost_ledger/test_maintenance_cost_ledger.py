# Copyright (c) 2026, afmcoltd
"""Tests for Maintenance Cost Ledger's post-insert immutability.

Patterned on frappe/tests/test_document.py. The row is built directly and
re-saved so ``on_update`` in ``maintenance_cost_ledger.py`` is what is
exercised, not a stub.

``Item``, ``Maintenance Material``, ``Maintenance Work Order`` and
``Maintenance Request`` are excluded from the dependency walk: no case here
sets any of the four, and each one's own closure reaches Purchase Invoice,
which resolves an unmigrated ``Payment Gateway`` and kills record-building
before a single test runs.
"""

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
