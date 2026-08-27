# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today

from apex.tests.factories import make_vehicle

_TABLE = "tabRental Accrual Ledger"
_KEY_COLUMNS = ["vehicle", "accrual_date", "is_reversal"]


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


def _rental_accrual_ledger(**overrides):
    fields = {
        "doctype": "Rental Accrual Ledger",
        "vehicle": make_vehicle("_T-RAL 0001"),
        "accrual_date": today(),
        "daily_rate": 100.0,
        "amount": 100.0,
    }
    fields.update(overrides)
    return frappe.get_doc(fields)


class TestRentalAccrualLedgerUniqueIndex(FrappeTestCase):
    def test_the_vehicle_date_and_reversal_flag_triple_carries_a_unique_index_in_the_database(self):
        self.assertEqual(
            _unique_index_columns(_TABLE, "unique_ral_vehicle_date"), _KEY_COLUMNS
        )


class TestRentalAccrualLedgerAccrualDay(FrappeTestCase):
    def test_the_accrual_of_the_next_day_is_accepted(self):
        first = _rental_accrual_ledger().insert(ignore_permissions=True)
        second = _rental_accrual_ledger(
            accrual_date=add_days(first.accrual_date, 1)
        ).insert(ignore_permissions=True)
        self.assertTrue(frappe.db.exists("Rental Accrual Ledger", second.name))


class TestRentalAccrualLedgerDoubleAccrual(FrappeTestCase):
    def test_a_second_accrual_for_the_same_vehicle_and_day_is_refused_by_the_database(self):
        first = _rental_accrual_ledger().insert(ignore_permissions=True)
        with self.assertRaisesRegex(
            frappe.UniqueValidationError, "unique_ral_vehicle_date"
        ):
            _rental_accrual_ledger(accrual_date=first.accrual_date).insert(
                ignore_permissions=True
            )


class TestRentalAccrualLedgerReversal(FrappeTestCase):
    def test_the_flag_is_derived_from_the_pointer_and_never_supplied(self):
        accrual = _rental_accrual_ledger(
            accrual_date=add_days(today(), 10), is_reversal=1
        ).insert(ignore_permissions=True)
        self.assertEqual(accrual.is_reversal, 0)

    def test_one_reversal_of_the_same_vehicle_and_day_is_accepted(self):
        accrual = _rental_accrual_ledger(
            accrual_date=add_days(today(), 20)
        ).insert(ignore_permissions=True)
        reversal = _rental_accrual_ledger(
            accrual_date=accrual.accrual_date,
            amount=-accrual.amount,
            reversal_of=accrual.name,
        ).insert(ignore_permissions=True)
        self.assertEqual(reversal.reversal_of, accrual.name)
        self.assertEqual(reversal.is_reversal, 1)

    def test_a_second_reversal_of_the_same_accrual_is_refused_by_the_database(self):
        accrual = _rental_accrual_ledger(
            accrual_date=add_days(today(), 30)
        ).insert(ignore_permissions=True)
        _rental_accrual_ledger(
            accrual_date=accrual.accrual_date,
            amount=-accrual.amount,
            reversal_of=accrual.name,
        ).insert(ignore_permissions=True)
        with self.assertRaisesRegex(
            frappe.UniqueValidationError, "unique_ral_vehicle_date"
        ):
            _rental_accrual_ledger(
                accrual_date=accrual.accrual_date,
                amount=-accrual.amount,
                reversal_of=accrual.name,
            ).insert(ignore_permissions=True)


class TestRentalAccrualLedgerMandatoryFields(FrappeTestCase):
    def test_an_accrual_with_no_date_is_refused_by_the_framework(self):
        doc = _rental_accrual_ledger(accrual_date=None)
        with self.assertRaises(frappe.MandatoryError):
            doc.insert(ignore_permissions=True)
