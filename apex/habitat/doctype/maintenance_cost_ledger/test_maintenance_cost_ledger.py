# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.habitat.doctype.maintenance_cost_ledger.maintenance_cost_ledger import (
    UNIQUE_KEY,
    UNIQUE_KEY_NAME,
)

test_dependencies = ["Building"]
test_ignore = [
    "Item",
    "Maintenance Material",
    "Maintenance Work Order",
    "Maintenance Request",
]


def _make_test_records(verbose=None):
    """Pin the test-record names so the live MCL- counter is never advanced."""
    from apex.tests._helpers import make_named_test_records

    return make_named_test_records("Maintenance Cost Ledger", "_T-MCL-")


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


def _unique_index_columns(table, index_name):
    rows = frappe.db.sql(
        """
        SELECT COLUMN_NAME AS col
        FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = %s
          AND INDEX_NAME = %s
          AND NON_UNIQUE = 0
        ORDER BY SEQ_IN_INDEX
        """,
        (table, index_name),
        as_dict=True,
    )
    return [row["col"] for row in rows]


class TestMaintenanceCostLedgerUniqueKey(FrappeTestCase):
    def _row(self, **fields):
        data = {
            "doctype": "Maintenance Cost Ledger",
            "posting_date": "2026-01-12",
            "building": "_Test Building",
            "item_description": "Plumbing repair parts",
            "amount": 250,
            "source_doctype": "Maintenance Work Order",
            "source_name": "_T-MWO-9101",
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

    def test_the_key_the_database_holds_is_the_key_the_controller_declares(self):
        self.assertEqual(_unique_index_columns("tabMaintenance Cost Ledger", UNIQUE_KEY_NAME), UNIQUE_KEY)

    def test_a_second_posting_of_one_procurement_line_is_refused_by_the_database(self):
        first = self._row()
        with self.assertRaisesRegex(frappe.UniqueValidationError, UNIQUE_KEY_NAME):
            self._row(source_name=first.source_name, source_detail_no=1)

    def test_another_line_of_the_same_work_order_is_accepted(self):
        first = self._row(source_name="_T-MWO-9102")
        second = self._row(source_name=first.source_name, source_detail_no=2)
        self.assertEqual(second.source_detail_no, 2)

    def test_one_reversal_of_a_line_is_accepted_and_a_second_is_refused(self):
        first = self._row(source_name="_T-MWO-9103")
        reversal = self._row(source_name=first.source_name, reversal_of=first.name)
        self.assertEqual(reversal.is_reversal, 1)
        with self.assertRaisesRegex(frappe.UniqueValidationError, UNIQUE_KEY_NAME):
            self._row(source_name=first.source_name, reversal_of=first.name)

    def test_the_flag_is_derived_from_the_pointer_and_never_supplied(self):
        row = self._row(source_name="_T-MWO-9104", is_reversal=1)
        self.assertEqual(row.is_reversal, 0)
