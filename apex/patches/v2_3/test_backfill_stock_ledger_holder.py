# Copyright (c) 2026, AFMCO and contributors
"""Tests for the Accommodation Stock Ledger party_type/party backfill.

``party_type``/``party`` are set at insert time by every current writer, so the
pre-migration shape (an employee holder with no party set) is forced here
through a direct ``db.set_value`` write on ``party`` after a normal insert --
the same gap the backfill exists to close.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.patches.v2_3.backfill_stock_ledger_holder import execute


def _h(n=10):
    return frappe.generate_hash(length=n).upper()


class TestBackfillStockLedgerHolder(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self.employee = "EMP-" + _h()
        self.building = "BLDG-" + _h()
        self._names = []

    def tearDown(self):
        for name in self._names:
            frappe.delete_doc(
                "Accommodation Stock Ledger", name, ignore_permissions=True, force=True
            )

    def _row(self, employee):
        doc = frappe.get_doc(
            {
                "doctype": "Accommodation Stock Ledger",
                "naming_series": "ACC-SLE-.YYYY.-.######",
                "posting_date": "2026-01-01",
                "item_type": "Maintenance Material",
                "item": "ITEM-" + _h(),
                "item_name": "item",
                "uom": "Nos",
                "signed_qty": 1,
                "building": self.building,
                "employee": employee,
                "is_cancelled": 0,
            }
        )
        doc.insert(ignore_permissions=True, ignore_links=True)
        self._names.append(doc.name)
        return doc.name

    def test_a_row_with_employee_and_no_party_is_backfilled(self):
        name = self._row(self.employee)
        frappe.db.set_value("Accommodation Stock Ledger", name, "party", None)
        frappe.db.set_value("Accommodation Stock Ledger", name, "party_type", None)
        frappe.db.commit()

        execute()

        row = frappe.db.get_value(
            "Accommodation Stock Ledger", name, ["party_type", "party"], as_dict=True
        )
        self.assertEqual(row.party_type, "Employee")
        self.assertEqual(row.party, self.employee)

    def test_a_row_that_already_carries_a_party_is_not_overwritten(self):
        """The WHERE clause only fills a BLANK party -- an existing (e.g. Temporary
        Worker) holder must survive the backfill untouched."""
        name = self._row(self.employee)
        frappe.db.set_value("Accommodation Stock Ledger", name, "party_type", "Temporary Worker")
        frappe.db.set_value("Accommodation Stock Ledger", name, "party", "TW-EXISTING")
        frappe.db.commit()

        execute()

        row = frappe.db.get_value(
            "Accommodation Stock Ledger", name, ["party_type", "party"], as_dict=True
        )
        self.assertEqual(row.party_type, "Temporary Worker")
        self.assertEqual(row.party, "TW-EXISTING")

    def test_a_row_with_no_employee_is_left_unbackfilled(self):
        name = self._row(None)
        frappe.db.set_value("Accommodation Stock Ledger", name, "party", None)
        frappe.db.set_value("Accommodation Stock Ledger", name, "party_type", None)
        frappe.db.commit()

        execute()

        row = frappe.db.get_value(
            "Accommodation Stock Ledger", name, ["party_type", "party"], as_dict=True
        )
        self.assertIsNone(row.party)
