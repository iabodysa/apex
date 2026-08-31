# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.salis.doctype.trip_fulfilment_ledger.trip_fulfilment_ledger import (
    UNIQUE_KEY,
    UNIQUE_KEY_NAME,
    on_doctype_update,
)


def _fulfilment_row(**overrides):
    fields = {
        "doctype": "Trip Fulfilment Ledger",
        "trip_date": frappe.utils.today(),
        "worker_count": 4,
        "source_doctype": "_T-TripFulfilmentLedger",
    }
    fields.update(overrides)
    return frappe.get_doc(fields)


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


def _make_test_records(verbose=None):
    """Pin the test-record names so the live TFL- counter is never advanced."""
    from apex.tests._helpers import make_named_test_records

    return make_named_test_records("Trip Fulfilment Ledger", "_T-TFL-")


class TestTripFulfilmentLedgerImmutability(FrappeTestCase):
    def test_a_posted_row_refuses_a_second_write(self):
        doc = _fulfilment_row(dispatch_trip="_T-DT-9001").insert(
            ignore_permissions=True, ignore_links=True
        )
        doc.worker_count = 9
        with self.assertRaises(frappe.PermissionError):
            doc.save(ignore_permissions=True)

    def test_a_first_write_is_accepted(self):
        doc = _fulfilment_row(dispatch_trip="_T-DT-9002").insert(
            ignore_permissions=True, ignore_links=True
        )
        self.assertEqual(doc.worker_count, 4)


class TestTripFulfilmentLedgerUniqueness(FrappeTestCase):
    def test_one_dispatch_trip_carries_a_unique_constraint(self):
        on_doctype_update()
        self.assertTrue(frappe.db.has_index("tabTrip Fulfilment Ledger", UNIQUE_KEY_NAME))

    def test_the_key_the_database_holds_is_the_key_the_controller_declares(self):
        on_doctype_update()
        self.assertEqual(
            _unique_index_columns("tabTrip Fulfilment Ledger", UNIQUE_KEY_NAME), UNIQUE_KEY
        )

    def test_a_second_fulfilment_of_one_trip_is_refused_by_the_database(self):
        first = _fulfilment_row(dispatch_trip="_T-DT-9201")
        first.insert(ignore_permissions=True, ignore_links=True)
        self.addCleanup(
            lambda name=first.name: frappe.db.delete("Trip Fulfilment Ledger", {"name": name})
        )
        with self.assertRaisesRegex(frappe.UniqueValidationError, UNIQUE_KEY_NAME):
            _fulfilment_row(dispatch_trip="_T-DT-9201").insert(
                ignore_permissions=True, ignore_links=True
            )


class TestTripFulfilmentLedgerReversal(FrappeTestCase):
    def _pair(self, trip):
        original = _fulfilment_row(dispatch_trip=trip)
        original.insert(ignore_permissions=True, ignore_links=True)
        self.addCleanup(
            lambda: frappe.db.delete("Trip Fulfilment Ledger", {"dispatch_trip": trip})
        )
        return original

    def test_a_reversal_of_a_posted_row_is_accepted_beside_it(self):
        original = self._pair("_T-DT-9301")
        reversal = _fulfilment_row(
            dispatch_trip="_T-DT-9301", worker_count=-4, reversal_of=original.name
        )
        reversal.insert(ignore_permissions=True, ignore_links=True)
        self.assertEqual(reversal.is_reversal, 1)
        self.assertTrue(frappe.db.exists("Trip Fulfilment Ledger", original.name))

    def test_a_row_naming_no_original_is_not_a_reversal(self):
        original = self._pair("_T-DT-9302")
        self.assertEqual(original.is_reversal, 0)

    def test_a_second_reversal_of_one_trip_is_refused_by_the_database(self):
        original = self._pair("_T-DT-9303")
        _fulfilment_row(
            dispatch_trip="_T-DT-9303", worker_count=-4, reversal_of=original.name
        ).insert(ignore_permissions=True, ignore_links=True)
        with self.assertRaisesRegex(frappe.UniqueValidationError, UNIQUE_KEY_NAME):
            _fulfilment_row(
                dispatch_trip="_T-DT-9303", worker_count=-4, reversal_of=original.name
            ).insert(ignore_permissions=True, ignore_links=True)
