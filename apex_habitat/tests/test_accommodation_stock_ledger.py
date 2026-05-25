# Copyright (c) 2026, AFMCO and contributors
"""Phase A — Accommodation Stock Ledger engine helpers: post_stock_entry resolves
item metadata and inserts a signed row; reverse_stock_entries posts a negative
mirror and marks the original cancelled; the doctype is read-only."""

import frappe
from frappe.utils import flt
from apex_habitat.tests.test_utils import ApexHabitatTestCase
from apex_habitat.habitat.doctype.accommodation_stock_ledger.accommodation_stock_ledger import (
    post_stock_entry, has_stock_entries, reverse_stock_entries,
)


def _h(n=4):
    return frappe.generate_hash(length=n).upper()


class TestAccommodationStockLedger(ApexHabitatTestCase):
    def setUp(self):
        self.company = frappe.db.get_value("Company", {}) or frappe.get_doc({
            "doctype": "Company", "company_name": "Test Co", "default_currency": "SAR",
            "country": "Saudi Arabia"}).insert(ignore_permissions=True).name
        self.cc = frappe.db.get_value("Cost Center", {"is_group": 0, "company": self.company}) or frappe.db.get_value("Cost Center", {"is_group": 0})
        self.site = frappe.get_doc({"doctype": "Accommodation Site", "site_name": _h(6)}).insert(ignore_permissions=True)
        self.building = frappe.get_doc({"doctype": "Accommodation Building", "building_name": "B " + _h(),
                                        "site": self.site.name, "total_capacity": 4, "company": self.company,
                                        "default_cost_center": self.cc}).insert(ignore_permissions=True).name
        cat = frappe.db.get_value("Custody Asset Category", {}) or frappe.get_doc({
            "doctype": "Custody Asset Category", "category_name": "Cat " + _h()}).insert(ignore_permissions=True).name
        self.article = frappe.get_doc({"doctype": "Custody Article", "naming_series": "ART-.####",
                                       "article_name": "Towel " + _h(), "category": cat,
                                       "unit_of_measure": "Nos", "standard_unit_cost_sar": 12}).insert(ignore_permissions=True)
        self.employee = frappe.get_doc({"doctype": "Employee", "first_name": "E " + _h(), "company": self.company,
                                        "gender": "Male", "date_of_birth": "1990-01-01", "date_of_joining": "2020-01-01"}).insert(ignore_permissions=True).name

    def test_post_resolves_metadata(self):
        name = post_stock_entry(item_type="Custody Article", item=self.article.name, qty=5,
                                building=self.building, employee=self.employee,
                                voucher_type="Test Voucher", voucher_no="TV-1", voucher_detail_no="r1")
        row = frappe.get_doc("Accommodation Stock Ledger", name)
        self.assertEqual(row.item_name, self.article.article_name)
        self.assertEqual(row.uom, "Nos")
        self.assertEqual(flt(row.unit_cost_sar), 12.0)
        self.assertEqual(flt(row.qty), 5.0)
        self.assertEqual(row.cost_center, self.cc)
        self.assertEqual(row.employee, self.employee)
        self.assertTrue(has_stock_entries("Test Voucher", "TV-1"))

    def test_reverse_negates_and_cancels(self):
        post_stock_entry(item_type="Custody Article", item=self.article.name, qty=8,
                         building=self.building, voucher_type="Test Voucher", voucher_no="TV-2")
        reverse_stock_entries("Test Voucher", "TV-2")
        rows = frappe.get_all("Accommodation Stock Ledger", filters={"voucher_no": "TV-2"},
                              fields=["qty", "is_cancelled", "reversal_of"])
        self.assertEqual(len(rows), 2)
        self.assertEqual(flt(sum(flt(r.qty) for r in rows)), 0.0, "net balance after reversal must be 0")
        self.assertTrue(any(r.reversal_of for r in rows), "a reversal entry must reference the original")
        self.assertFalse(has_stock_entries("Test Voucher", "TV-2"), "no live entries remain after reversal")

    def test_engine_is_read_only(self):
        meta = frappe.get_meta("Accommodation Stock Ledger")
        self.assertFalse(any(p.create for p in meta.permissions), "stock ledger must be read-only (no create)")
