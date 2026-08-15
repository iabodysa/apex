# Copyright (c) 2026, afmcoltd
"""Custody Issue and Custody Return post to the Accommodation Stock Ledger: an issue moves stock
from the building store into an employee's custody, a return moves it back, a cancel reverses it,
and a receipt whose goods have already left the store may not be cancelled at all.

The two buildings, the article and the employee all come from ``test_records.json`` — the second
fixture building already carries ``is_procurement_store``, which is what the Goods Receipt case
needs. The previous form of this file built a Company, a Site, two Buildings, a Custody Asset
Category, a Custody Article and an Employee in ``setUp``, per test method.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from apex.habitat.doctype.accommodation_stock_ledger.accommodation_stock_ledger import (
    get_store_balance,
    has_stock_entries,
    post_stock_entry,
)

test_dependencies = ["Building", "Custody Article", "Employee"]

BUILDING = "_Test Building"
PROCUREMENT_STORE = "_Test Building 2"


class TestCustodyStockIntegration(FrappeTestCase):
    def setUp(self):
        self.article = frappe.db.get_value("Custody Article", {"article_name": "_Test Blanket"})
        self.employee = frappe.db.get_value("Employee", {"first_name": "_Test Employee"})
        # FrappeTestCase rolls the database back once per CLASS, not once per method —
        # frappe/tests/utils.py:46 registers _rollback_db with addClassCleanup — so stock a case
        # leaves in a shared fixture store would become the next case's opening balance. A
        # savepoint is the framework's own way to hand the store back exactly as it was found.
        frappe.db.savepoint("apex_custody_stock_case")
        self.addCleanup(frappe.db.rollback, save_point="apex_custody_stock_case")

    def _balance(self, building, employee=None):
        filters = {"item": self.article, "building": building, "is_cancelled": 0}
        filters["employee"] = employee if employee else ["is", "not set"]
        rows = frappe.get_all("Accommodation Stock Ledger", filters=filters, fields=["signed_qty"])
        return flt(sum(flt(r.signed_qty) for r in rows))

    def _stock_the_store(self, building, qty):
        post_stock_entry(
            item_type="Custody Article", item=self.article, qty=qty, building=building,
            voucher_type="Opening Stock", voucher_no="OPEN-" + frappe.generate_hash(length=12).upper(),
        )

    def _issue(self, qty=5, building=BUILDING, stock_first=True):
        if stock_first:
            self._stock_the_store(building, qty)
        doc = frappe.get_doc({
            "doctype": "Custody Issue",
            "naming_series": "CUST-ISS-.####",
            "issue_date": "2026-05-01",
            "issued_to_employee": self.employee,
            "building": building,
        })
        doc.append("items", {"article": self.article, "qty": qty})
        doc.insert(ignore_permissions=True)
        doc.submit()
        return doc

    def test_an_issue_moves_stock_into_custody_and_a_return_moves_it_back(self):
        issue = self._issue(5)
        self.assertEqual(self._balance(BUILDING, self.employee), 5.0)
        self.assertEqual(self._balance(BUILDING), 0.0)

        returned = frappe.get_doc({
            "doctype": "Custody Return",
            "naming_series": "CUST-RET-.####",
            "return_date": "2026-05-10",
            "custody_issue": issue.name,
            "returned_by_employee": self.employee,
            "building": BUILDING,
        })
        returned.append("items", {"article": self.article, "qty": 5})
        returned.insert(ignore_permissions=True)
        returned.submit()

        self.assertEqual(self._balance(BUILDING, self.employee), 0.0)
        self.assertEqual(self._balance(BUILDING), 5.0)

    def test_cancelling_an_issue_reverses_the_stock_it_moved(self):
        issue = self._issue(3)
        self.assertTrue(has_stock_entries("Custody Issue", issue.name))

        issue.reload()
        issue.cancel()

        self.assertFalse(has_stock_entries("Custody Issue", issue.name))
        self.assertEqual(self._balance(BUILDING, self.employee), 0.0)

    def test_a_receipt_whose_goods_have_been_issued_out_may_not_be_cancelled(self):
        """Cancelling a receipt whose goods already left the store must be refused, not mirrored:
        the reversal would drive the store negative and invent stock that is physically in an
        employee's hands. Nothing may be written on refusal."""
        receipt = frappe.get_doc({
            "doctype": "Goods Receipt",
            "naming_series": "ACC-GRN-.YYYY.-.#####",
            "receipt_date": "2026-05-01",
            "intake_building": PROCUREMENT_STORE,
            "procurement_supervisor": "Administrator",
        })
        receipt.append("items", {"item_type": "Custody Article", "item": self.article, "qty": 10})
        receipt.insert(ignore_permissions=True)
        receipt.submit()
        self.assertEqual(get_store_balance("Custody Article", self.article, PROCUREMENT_STORE), 10.0)

        self._issue(10, building=PROCUREMENT_STORE, stock_first=False)
        self.assertEqual(get_store_balance("Custody Article", self.article, PROCUREMENT_STORE), 0.0)

        receipt.reload()
        with self.assertRaises(frappe.ValidationError):
            receipt.cancel()

        # The refusal fires in before_cancel, which Frappe runs from run_before_save_methods()
        # BEFORE db_update() stamps docstatus 2. Raised from on_cancel instead, the 2 is already
        # written in the open transaction and every read for the rest of the request sees the
        # receipt as cancelled. Reading the row, not the in-memory object: Document._cancel()
        # assigns self.docstatus = 2 before save() is ever called, so the Python attribute is 2
        # either way and proves nothing.
        self.assertEqual(
            frappe.db.get_value("Goods Receipt", receipt.name, "docstatus"), 1,
            "a refused cancel must leave the receipt submitted, not cancelled-in-the-row",
        )
        receipt.reload()
        self.assertEqual(
            receipt.docstatus, 1,
            "reloading the receipt in the same request must still read it as submitted",
        )
        self.assertGreaterEqual(
            get_store_balance("Custody Article", self.article, PROCUREMENT_STORE), 0.0,
            "a refused reversal must never drive the building store negative",
        )
        self.assertEqual(
            frappe.db.count(
                "Accommodation Stock Ledger",
                {"voucher_no": receipt.name, "reversal_of": ["is", "set"]},
            ),
            0,
            "a refused reversal must write no mirror row for the cancelled voucher",
        )
