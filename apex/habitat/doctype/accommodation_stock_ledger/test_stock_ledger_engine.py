# Copyright (c) 2026, afmcoltd
"""The Accommodation Stock Ledger engine: post_stock_entry resolves the item's metadata and
writes one signed row, reverse_stock_entries posts the negative mirror, and nobody may create a
row by hand.

The building, the article and the employee all come from ``test_records.json`` rather than a
Company, a Site, a Building, a Custody Asset Category, a Custody Article and an Employee built in
``setUp`` per test method, to post two ledger rows.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from apex.habitat.doctype.accommodation_stock_ledger.accommodation_stock_ledger import (
    has_stock_entries,
    post_stock_entry,
    reverse_stock_entries,
)

test_dependencies = ["Building", "Custody Article", "Employee"]

BUILDING = "_Test Building"


class TestAccommodationStockLedger(FrappeTestCase):
    def setUp(self):
        self.article = frappe.db.get_value("Custody Article", {"article_name": "_Test Blanket"})
        self.employee = frappe.db.get_value("Employee", {"first_name": "_Test Employee"})
        self.cost_center = frappe.db.get_value("Building", BUILDING, "default_cost_center")

    def test_a_posted_entry_carries_the_item_metadata_it_resolved(self):
        name = post_stock_entry(
            item_type="Custody Article", item=self.article, qty=5, building=BUILDING,
            employee=self.employee, voucher_type="Test Voucher", voucher_no="TV-1",
            voucher_detail_no="r1",
        )
        row = frappe.get_doc("Accommodation Stock Ledger", name)

        self.assertEqual(row.item_name, "_Test Blanket")
        self.assertEqual(row.uom, frappe.db.get_value("Custody Article", self.article, "unit_of_measure"))
        self.assertEqual(flt(row.unit_cost), 12.0)
        self.assertEqual(flt(row.signed_qty), 5.0)
        self.assertEqual(row.cost_center, self.cost_center)
        self.assertEqual(row.employee, self.employee)
        self.assertTrue(has_stock_entries("Test Voucher", "TV-1"))

    def test_a_reversal_nets_the_voucher_to_zero_and_leaves_nothing_live(self):
        post_stock_entry(
            item_type="Custody Article", item=self.article, qty=8, building=BUILDING,
            voucher_type="Test Voucher", voucher_no="TV-2",
        )
        reverse_stock_entries("Test Voucher", "TV-2")

        rows = frappe.get_all(
            "Accommodation Stock Ledger",
            filters={"voucher_no": "TV-2"},
            fields=["signed_qty", "is_cancelled", "reversal_of"],
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual(flt(sum(flt(r.signed_qty) for r in rows)), 0.0)
        self.assertTrue(any(r.reversal_of for r in rows), "a reversal entry must reference the original")
        self.assertFalse(has_stock_entries("Test Voucher", "TV-2"), "no live entries remain after reversal")

    def test_a_drain_entry_carries_a_negative_signed_quantity(self):
        # The engine refuses to move more out of a holder than the holder has, so the custody the
        # drain empties is filled first: posting the -3 straight against an employee holding
        # nothing would be refused by that policy instead of exercised.
        post_stock_entry(
            item_type="Custody Article", item=self.article, qty=3, building=BUILDING,
            employee=self.employee, voucher_type="Test Voucher", voucher_no="TV-NEG-0",
        )
        name = post_stock_entry(
            item_type="Custody Article", item=self.article, qty=-3, building=BUILDING,
            employee=self.employee, voucher_type="Test Voucher", voucher_no="TV-NEG-1",
            voucher_detail_no="r1",
        )

        self.assertLess(flt(frappe.db.get_value("Accommodation Stock Ledger", name, "signed_qty")), 0)

    def test_the_ledger_grants_nobody_create(self):
        meta = frappe.get_meta("Accommodation Stock Ledger")
        self.assertFalse(any(p.create for p in meta.permissions), "stock ledger must be read-only")
