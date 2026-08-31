# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.habitat.doctype.facility_asset_movement_ledger.facility_asset_movement_ledger import (
    UNIQUE_KEY,
    UNIQUE_KEY_NAME,
)

test_dependencies = ["Building"]
test_ignore = ["Facility Asset"]


def _make_test_records(verbose=None):
    """Pin the test-record names so the live FAML- counter is never advanced."""
    from apex.tests._helpers import make_named_test_records

    return make_named_test_records("Facility Asset Movement Ledger", "_T-FAML-")


class TestFacilityAssetMovementLedgerImmutability(FrappeTestCase):
    def _row(self, **fields):
        data = {
            "doctype": "Facility Asset Movement Ledger",
            "posting_datetime": "2026-01-10 08:00:00",
            "from_building": "_Test Building",
            "to_building": "_Test Building 2",
            "source_doctype": "Facility Asset Movement",
            "source_name": "_T-FAM-9001",
        }
        data.update(fields)
        doc = frappe.get_doc(data)
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.addCleanup(
            lambda name=doc.name: frappe.db.delete(
                "Facility Asset Movement Ledger", {"name": name}
            )
        )
        return doc

    def test_editing_a_posted_row_after_insert_is_refused(self):
        doc = self._row()
        doc.to_location = "Rewritten"
        with self.assertRaises(frappe.PermissionError):
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


class TestFacilityAssetMovementLedgerUniqueKey(FrappeTestCase):
    def _row(self, **fields):
        data = {
            "doctype": "Facility Asset Movement Ledger",
            "posting_datetime": "2026-01-10 08:00:00",
            "from_building": "_Test Building",
            "to_building": "_Test Building 2",
            "source_doctype": "Facility Asset Movement",
            "source_name": "_T-FAM-9101",
        }
        data.update(fields)
        doc = frappe.get_doc(data)
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.addCleanup(
            lambda name=doc.name: frappe.db.delete(
                "Facility Asset Movement Ledger", {"name": name}
            )
        )
        return doc

    def test_the_key_the_database_holds_is_the_key_the_controller_declares(self):
        self.assertEqual(_unique_index_columns("tabFacility Asset Movement Ledger", UNIQUE_KEY_NAME), UNIQUE_KEY)

    def test_a_second_posting_from_one_movement_is_refused_by_the_database(self):
        first = self._row()
        with self.assertRaisesRegex(frappe.UniqueValidationError, UNIQUE_KEY_NAME):
            self._row(source_name=first.source_name)

    def test_one_reversal_of_a_posting_is_accepted_and_a_second_is_refused(self):
        first = self._row(source_name="_T-FAM-9102")
        reversal = self._row(source_name=first.source_name, reversal_of=first.name)
        self.assertEqual(reversal.is_reversal, 1)
        with self.assertRaisesRegex(frappe.UniqueValidationError, UNIQUE_KEY_NAME):
            self._row(source_name=first.source_name, reversal_of=first.name)

    def test_the_flag_is_derived_from_the_pointer_and_never_supplied(self):
        row = self._row(source_name="_T-FAM-9103", is_reversal=1)
        self.assertEqual(row.is_reversal, 0)
