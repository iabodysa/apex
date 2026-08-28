# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.habitat.doctype.accommodation_ledger.accommodation_ledger import (
    UNIQUE_KEY,
    UNIQUE_KEY_NAME,
)

test_dependencies = ["Building", "Employee"]
test_ignore = ["Project"]


class TestAccommodationLedgerPartyMirroring(FrappeTestCase):
    def test_an_employee_party_is_mirrored_onto_the_employee_column(self):
        doc = frappe.get_doc(
            {
                "doctype": "Accommodation Ledger",
                "posting_date": "2026-01-15",
                "ledger_type": "Rent",
                "building": "_Test Building",
                "party_type": "Employee",
                "party": "_T-Employee-00001",
                "source_doctype": "Housing Assignment",
                "source_name": "_T-HA-9001",
            }
        )
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.addCleanup(
            lambda name=doc.name: frappe.db.delete("Accommodation Ledger", {"name": name})
        )
        self.assertEqual(doc.employee, "_T-Employee-00001")


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


class TestAccommodationLedgerUniqueKey(FrappeTestCase):
    def _row(self, **fields):
        data = {
            "doctype": "Accommodation Ledger",
            "posting_date": "2026-02-01",
            "ledger_type": "Rent",
            "building": "_Test Building",
            "source_doctype": "Housing Assignment",
            "source_name": "_T-HA-9101",
        }
        data.update(fields)
        doc = frappe.get_doc(data)
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.addCleanup(
            lambda name=doc.name: frappe.db.delete("Accommodation Ledger", {"name": name})
        )
        return doc

    def test_the_key_the_database_holds_is_the_key_the_controller_declares(self):
        self.assertEqual(_unique_index_columns("tabAccommodation Ledger", UNIQUE_KEY_NAME), UNIQUE_KEY)

    def test_a_second_share_for_one_source_day_and_type_is_refused_by_the_database(self):
        first = self._row()
        with self.assertRaisesRegex(frappe.UniqueValidationError, UNIQUE_KEY_NAME):
            self._row(source_name=first.source_name)

    def test_a_memo_row_that_carries_no_employee_is_still_guarded(self):
        first = self._row(source_doctype="Utility Bill Entry", source_name="_T-UBE-9101", ledger_type="Electricity")
        self.assertFalse(first.employee)
        with self.assertRaisesRegex(frappe.UniqueValidationError, UNIQUE_KEY_NAME):
            self._row(source_doctype="Utility Bill Entry", source_name="_T-UBE-9101", ledger_type="Electricity")

    def test_another_cost_type_of_the_same_source_and_day_is_accepted(self):
        first = self._row(source_name="_T-HA-9102")
        second = self._row(source_name=first.source_name, ledger_type="Water")
        self.assertEqual(second.ledger_type, "Water")

    def test_the_next_day_of_the_same_source_and_type_is_accepted(self):
        first = self._row(source_name="_T-HA-9103")
        second = self._row(source_name=first.source_name, posting_date="2026-02-02")
        self.assertEqual(str(second.posting_date), "2026-02-02")

    def test_one_reversal_of_a_row_is_accepted_and_a_second_is_refused(self):
        first = self._row(source_name="_T-HA-9104")
        reversal = self._row(source_name=first.source_name, reversal_of=first.name)
        self.assertEqual(reversal.is_reversal, 1)
        with self.assertRaisesRegex(frappe.UniqueValidationError, UNIQUE_KEY_NAME):
            self._row(source_name=first.source_name, reversal_of=first.name)

    def test_the_flag_is_derived_from_the_pointer_and_never_supplied(self):
        row = self._row(source_name="_T-HA-9105", is_reversal=1)
        self.assertEqual(row.is_reversal, 0)
