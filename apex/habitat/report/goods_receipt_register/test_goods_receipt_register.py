# Copyright (c) 2026, afmcoltd

"""Tests for the Goods Receipt Register report.

Pins the report's mechanical contract: every column's fieldname must be a key
on each item-line row ``execute()`` returns, and the building scope guard
must confine a scoped caller holding no Building User Permission to zero
rows while still handing back the column definitions.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.habitat.report.goods_receipt_register.goods_receipt_register import execute
from apex.tests._helpers import _user, as_user
from apex.tests.factories import default_company, make_building, make_goods_receipt


def _article(article_name):
    """Get-or-create a Custody Article by name; return its name."""
    existing = frappe.db.get_value("Custody Article", {"article_name": article_name}, "name")
    if existing:
        return existing
    return (
        frappe.get_doc(
            {"doctype": "Custody Article", "article_name": article_name, "unit_of_measure": "Nos"}
        )
        .insert(ignore_permissions=True, ignore_mandatory=True)
        .name
    )


class TestGoodsReceiptRegister(FrappeTestCase):
    """Exercises the register's column/row contract and its building scope guard."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.building = make_building(
            "A564 GRR Building", company=default_company(), is_procurement_store=1
        ).name
        cls.article = _article("A564 GRR Article")
        cls.receipt = make_goods_receipt(cls.building, cls.article, "Administrator", qty=3)

    def setUp(self):
        """Runs every case as Administrator, regardless of what the previous case switched to."""
        frappe.set_user("Administrator")

    def tearDown(self):
        """Restores the Administrator session after a case that switched users."""
        frappe.set_user("Administrator")

    def test_columns_and_row_fieldnames_agree(self):
        """Every column's fieldname must be a key on each item row execute() returns."""
        columns, rows, _chart, _report_summary, _summary = execute({"building": self.building})

        self.assertTrue(rows, "the fixture receipt's line must be visible to an unscoped caller")
        fieldnames = {column["fieldname"] for column in columns}
        for row in rows:
            missing = fieldnames - set(row.keys())
            self.assertEqual(missing, set(), f"row is missing declared column fieldnames: {missing}")

    def test_out_of_scope_caller_gets_columns_and_no_rows(self):
        """A building-scoped caller holding no Building User Permission sees zero rows."""
        outsider = _user("a564-grr-outsider@test.local", "Resident Supervisor")
        with as_user(outsider):
            columns, rows, _chart, _report_summary, summary = execute({"building": self.building})

        self.assertTrue(columns, "columns must still be returned to an out-of-scope caller")
        self.assertEqual(rows, [])
        self.assertEqual(summary[0]["value"], 0)
