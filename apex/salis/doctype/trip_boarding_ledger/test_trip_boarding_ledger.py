# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.salis.doctype.trip_boarding_ledger.trip_boarding_ledger import (
    UNIQUE_KEY,
    UNIQUE_KEY_NAME,
    on_doctype_update,
)


def _boarding_row(**overrides):
    fields = {
        "doctype": "Trip Boarding Ledger",
        "posting_date": frappe.utils.today(),
        "outcome": "Boarded",
        "confirm_source": "_T-TripBoardingLedger",
    }
    fields.update(overrides)
    return frappe.get_doc(fields)


class TestTripBoardingLedgerImmutability(FrappeTestCase):
    def test_a_posted_row_refuses_a_second_write(self):
        doc = _boarding_row(
            dispatch_trip="_T-DT-9001", employee="_T-Employee-00001"
        ).insert(ignore_permissions=True, ignore_links=True)
        doc.outcome = "Missed"
        with self.assertRaises(frappe.PermissionError):
            doc.save(ignore_permissions=True)

    def test_a_first_write_is_accepted(self):
        doc = _boarding_row(
            dispatch_trip="_T-DT-9002", employee="_T-Employee-00001"
        ).insert(ignore_permissions=True, ignore_links=True)
        self.assertEqual(doc.outcome, "Boarded")


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


class TestTripBoardingLedgerUniqueness(FrappeTestCase):
    def _row(self, **overrides):
        fields = {
            "dispatch_trip": "_T-DT-9101",
            "employee": "_T-Employee-00001",
        }
        fields.update(overrides)
        doc = _boarding_row(**fields)
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.addCleanup(
            lambda name=doc.name: frappe.db.delete("Trip Boarding Ledger", {"name": name})
        )
        return doc

    def test_the_trip_and_employee_pair_carries_a_unique_constraint(self):
        on_doctype_update()
        self.assertTrue(
            frappe.db.has_index("tabTrip Boarding Ledger", UNIQUE_KEY_NAME)
        )

    def test_the_key_the_database_holds_is_the_key_the_controller_declares(self):
        self.assertEqual(_unique_index_columns("tabTrip Boarding Ledger", UNIQUE_KEY_NAME), UNIQUE_KEY)

    def test_a_second_terminal_row_for_one_worker_on_one_trip_is_refused(self):
        first = self._row()
        with self.assertRaisesRegex(frappe.UniqueValidationError, UNIQUE_KEY_NAME):
            self._row(dispatch_trip=first.dispatch_trip, employee=first.employee)

    def test_one_reversal_of_a_boarding_is_accepted_and_a_second_is_refused(self):
        first = self._row(dispatch_trip="_T-DT-9102")
        reversal = self._row(
            dispatch_trip=first.dispatch_trip,
            employee=first.employee,
            reversal_of=first.name,
        )
        self.assertEqual(reversal.is_reversal, 1)
        with self.assertRaisesRegex(frappe.UniqueValidationError, UNIQUE_KEY_NAME):
            self._row(
                dispatch_trip=first.dispatch_trip,
                employee=first.employee,
                reversal_of=first.name,
            )

    def test_the_flag_is_derived_from_the_pointer_and_never_supplied(self):
        row = self._row(dispatch_trip="_T-DT-9103", is_reversal=1)
        self.assertEqual(row.is_reversal, 0)
