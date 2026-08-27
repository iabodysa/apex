# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.apex_core.utils.ledger_index import _constraint_exists
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


class TestTripFulfilmentLedgerImmutability(FrappeTestCase):
    def test_a_posted_row_refuses_a_second_write(self):
        doc = _fulfilment_row().insert(ignore_permissions=True)
        doc.worker_count = 9
        with self.assertRaises(frappe.PermissionError):
            doc.save(ignore_permissions=True)

    def test_a_first_write_is_accepted(self):
        doc = _fulfilment_row().insert(ignore_permissions=True)
        self.assertEqual(doc.worker_count, 4)


class TestTripFulfilmentLedgerUniqueness(FrappeTestCase):
    def test_one_dispatch_trip_carries_a_unique_constraint(self):
        on_doctype_update()
        self.assertTrue(_constraint_exists("Trip Fulfilment Ledger", UNIQUE_KEY_NAME))

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
