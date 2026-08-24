# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today

from apex.habitat.doctype.accommodation_stock_ledger.accommodation_stock_ledger import (
    _resolve_holder,
    get_store_balance,
)

test_dependencies = ["Building", "Custody Article"]

ITEM_TYPE = "Custody Article"
BUILDING = "_Test Building"


class TestAccommodationStockLedgerHolderResolution(FrappeTestCase):
    def test_a_bare_party_with_no_party_type_is_read_as_employee(self):
        party_type, party, employee = _resolve_holder(None, None, "HR-EMP-0001")
        self.assertEqual(
            (party_type, party, employee), ("Employee", "HR-EMP-0001", "HR-EMP-0001")
        )

    def test_a_legacy_employee_argument_becomes_the_party(self):
        party_type, party, employee = _resolve_holder("HR-EMP-0001", None, None)
        self.assertEqual(
            (party_type, party, employee), ("Employee", "HR-EMP-0001", "HR-EMP-0001")
        )

    def test_an_employee_party_type_fills_the_employee_column_from_the_party(self):
        party_type, party, employee = _resolve_holder(None, "Employee", "HR-EMP-0002")
        self.assertEqual(
            (party_type, party, employee), ("Employee", "HR-EMP-0002", "HR-EMP-0002")
        )

    def test_a_non_employee_party_never_writes_the_employee_column(self):
        party_type, party, employee = _resolve_holder(
            None, "Temporary Worker", "TW-0001"
        )
        self.assertEqual(
            (party_type, party, employee), ("Temporary Worker", "TW-0001", None)
        )

    def test_no_holder_at_all_resolves_to_the_unassigned_building_store(self):
        self.assertEqual(_resolve_holder(None, None, None), (None, None, None))


class TestAccommodationStockLedgerStoreBalance(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.item = frappe.db.get_value(
            "Custody Article", {"article_name": "_Test Ledger Article"}, "name"
        )

    def _post(self, qty, **fields):
        doc = frappe.get_doc(
            {
                "doctype": "Accommodation Stock Ledger",
                "posting_date": today(),
                "item_type": ITEM_TYPE,
                "item": self.item,
                "building": BUILDING,
                "signed_qty": qty,
                "voucher_type": "Test Voucher",
                "voucher_no": "TV-BALANCE-TEST",
            }
        )
        doc.update(fields)
        doc.insert(ignore_permissions=True)
        self.addCleanup(
            lambda name=doc.name: frappe.delete_doc(
                "Accommodation Stock Ledger", name, ignore_permissions=True, force=True
            )
        )
        return doc

    def test_the_store_balance_is_the_signed_sum_of_its_live_rows(self):
        baseline = get_store_balance(ITEM_TYPE, self.item, BUILDING)
        self._post(10)
        self._post(-3)
        self.assertEqual(
            get_store_balance(ITEM_TYPE, self.item, BUILDING), baseline + 7
        )

    def test_a_cancelled_row_does_not_count_toward_the_balance(self):
        baseline = get_store_balance(ITEM_TYPE, self.item, BUILDING)
        self._post(5)
        self._post(20, is_cancelled=1)
        self.assertEqual(
            get_store_balance(ITEM_TYPE, self.item, BUILDING), baseline + 5
        )
