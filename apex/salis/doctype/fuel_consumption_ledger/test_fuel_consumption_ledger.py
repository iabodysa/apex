# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import now_datetime

from apex.salis.doctype.fuel_consumption_ledger.fuel_consumption_ledger import (
    UNIQUE_KEY,
    UNIQUE_KEY_NAME,
)
from apex.tests.factories import make_vehicle

_TABLE = "tabFuel Consumption Ledger"
_KEY_COLUMNS = UNIQUE_KEY


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


def _fuel_consumption_ledger(**overrides):
    fields = {
        "doctype": "Fuel Consumption Ledger",
        "vehicle": make_vehicle("_T-FCL 0001"),
        "period_month": "2026-08",
        "litres": 40.0,
        "amount": 92.0,
        "logged_at": now_datetime(),
        "source_type": "Fuel Request",
        "source_doctype": "Fuel Request",
        "source_name": "_T-FCL-" + frappe.generate_hash(length=8),
    }
    fields.update(overrides)
    return frappe.get_doc(fields)


class TestFuelConsumptionLedgerUniqueIndex(FrappeTestCase):
    def test_the_key_the_database_holds_is_the_key_the_controller_declares(self):
        self.assertEqual(
            _unique_index_columns(_TABLE, UNIQUE_KEY_NAME), _KEY_COLUMNS
        )


class TestFuelConsumptionLedgerDoublePost(FrappeTestCase):
    def test_a_second_post_from_the_same_source_is_refused_by_the_database(self):
        first = _fuel_consumption_ledger().insert(ignore_permissions=True)
        second = _fuel_consumption_ledger(
            source_type=first.source_type,
            source_name=first.source_name,
            litres=1.0,
            amount=2.0,
        )
        with self.assertRaisesRegex(frappe.UniqueValidationError, UNIQUE_KEY_NAME):
            second.insert(ignore_permissions=True)

    def test_the_same_source_name_under_another_source_type_is_accepted(self):
        first = _fuel_consumption_ledger().insert(ignore_permissions=True)
        second = _fuel_consumption_ledger(
            source_type="Fuel Daily Log",
            source_doctype="Fuel Daily Log",
            source_name=first.source_name,
        ).insert(ignore_permissions=True)
        self.assertEqual(second.source_name, first.source_name)

    def test_a_post_from_a_different_source_name_is_accepted(self):
        _fuel_consumption_ledger().insert(ignore_permissions=True)
        second = _fuel_consumption_ledger().insert(ignore_permissions=True)
        self.assertTrue(frappe.db.exists("Fuel Consumption Ledger", second.name))

    def test_one_reversal_carrying_the_same_source_is_accepted_and_a_second_is_refused(self):
        first = _fuel_consumption_ledger().insert(ignore_permissions=True)
        reversal = _fuel_consumption_ledger(
            source_type=first.source_type,
            source_name=first.source_name,
            reversal_of=first.name,
            litres=-first.litres,
            amount=-first.amount,
        ).insert(ignore_permissions=True)
        self.assertEqual(reversal.is_reversal, 1)
        with self.assertRaisesRegex(frappe.UniqueValidationError, UNIQUE_KEY_NAME):
            _fuel_consumption_ledger(
                source_type=first.source_type,
                source_name=first.source_name,
                reversal_of=first.name,
                litres=-first.litres,
                amount=-first.amount,
            ).insert(ignore_permissions=True)

    def test_the_flag_is_derived_from_the_pointer_and_never_supplied(self):
        row = _fuel_consumption_ledger(is_reversal=1).insert(ignore_permissions=True)
        self.assertEqual(row.is_reversal, 0)


class TestFuelConsumptionLedgerSourceType(FrappeTestCase):
    def test_a_source_type_outside_the_select_options_is_refused_by_the_framework(self):
        doc = _fuel_consumption_ledger(source_type="Hand Entry")
        with self.assertRaises(frappe.ValidationError):
            doc.insert(ignore_permissions=True)
