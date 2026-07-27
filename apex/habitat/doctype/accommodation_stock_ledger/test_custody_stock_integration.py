# Copyright (c) 2026, AFMCO and contributors
"""Phase B — Custody Issue/Return post to the Accommodation Stock Ledger:
issue moves stock Store -> Employee custody (same building); return moves it
back; cancel reverses. Balance = sum(qty) where is_cancelled = 0."""

import frappe
from frappe.utils import flt
from apex.tests.factories import ApexHabitatTestCase


def _h(n=12):
    return frappe.generate_hash(length=n).upper()


def _bal(article, building, employee=None):
    filters = {"item": article, "building": building, "is_cancelled": 0}
    filters["employee"] = employee if employee else ["is", "not set"]
    rows = frappe.get_all("Accommodation Stock Ledger", filters=filters, fields=["signed_qty"])
    return flt(sum(flt(r.signed_qty) for r in rows))


class TestCustodyStockIntegration(ApexHabitatTestCase):
    def setUp(self):
        self.company = frappe.db.get_value("Company", {}) or frappe.get_doc({
            "doctype": "Company", "company_name": "Test Co", "default_currency": "SAR",
            "country": "Saudi Arabia"}).insert(ignore_permissions=True).name
        cc = frappe.db.get_value("Cost Center", {"is_group": 0, "company": self.company}) or frappe.db.get_value("Cost Center", {"is_group": 0})
        self.site = frappe.get_doc({"doctype": "Site", "site_name": _h(12)}).insert(ignore_permissions=True)
        self.building = frappe.get_doc({"doctype": "Building", "building_name": "B " + _h(),
                                        "site": self.site.name, "total_capacity": 4, "company": self.company,
                                        "default_cost_center": cc}).insert(ignore_permissions=True).name
        cat = frappe.db.get_value("Custody Asset Category", {}) or frappe.get_doc({
            "doctype": "Custody Asset Category", "category_name": "Cat " + _h()}).insert(ignore_permissions=True).name
        self.article = frappe.get_doc({"doctype": "Custody Article", "naming_series": "ART-.####",
                                       "article_name": "Item " + _h(), "category": cat,
                                       "unit_of_measure": "Nos"}).insert(ignore_permissions=True).name
        self.emp = frappe.get_doc({"doctype": "Employee", "first_name": "E " + _h(), "company": self.company,
                                   "gender": "Male", "date_of_birth": "1990-01-01", "date_of_joining": "2020-01-01"}).insert(ignore_permissions=True).name

    def _stock_store(self, qty):
        """Receive opening stock into the building store so an issue can draw it.
        Custody Issue now rejects issuing more than the store holds."""
        from apex.habitat.doctype.accommodation_stock_ledger.accommodation_stock_ledger import (
            post_stock_entry,
        )
        post_stock_entry(item_type="Custody Article", item=self.article, qty=qty,
                         building=self.building, voucher_type="Opening Stock",
                         voucher_no="OPEN-" + _h())

    def _issue(self, qty=5):
        self._stock_store(qty)
        i = frappe.get_doc({"doctype": "Custody Issue", "naming_series": "CUST-ISS-.####",
                            "issue_date": "2026-05-01", "issued_to_employee": self.emp, "building": self.building})
        i.append("items", {"article": self.article, "qty": qty})
        i.insert(ignore_permissions=True)
        i.submit()
        return i

    def test_issue_moves_to_custody_then_return_to_store(self):
        issue = self._issue(5)
        # [#3of7lf]
        self.assertEqual(_bal(self.article, self.building, self.emp), 5.0)
        self.assertEqual(_bal(self.article, self.building, None), 0.0)

        ret = frappe.get_doc({"doctype": "Custody Return", "naming_series": "CUST-RET-.####",
                              "return_date": "2026-05-10", "custody_issue": issue.name,
                              "returned_by_employee": self.emp, "building": self.building})
        ret.append("items", {"article": self.article, "qty": 5})
        ret.insert(ignore_permissions=True)
        ret.submit()
        # [#r2w6f4]
        self.assertEqual(_bal(self.article, self.building, self.emp), 0.0)
        self.assertEqual(_bal(self.article, self.building, None), 5.0)

    def test_cancel_issue_reverses_stock(self):
        from apex.habitat.doctype.accommodation_stock_ledger.accommodation_stock_ledger import has_stock_entries
        issue = self._issue(3)
        self.assertTrue(has_stock_entries("Custody Issue", issue.name))
        issue.reload()
        issue.cancel()
        self.assertFalse(has_stock_entries("Custody Issue", issue.name))
        self.assertEqual(_bal(self.article, self.building, self.emp), 0.0)

    def _procurement_building(self):
        """A building flagged as a procurement intake store, so a Goods Receipt can
        book stock into it and a Custody Issue can draw it out of the same store."""
        cc = frappe.db.get_value("Cost Center", {"is_group": 0, "company": self.company}) or frappe.db.get_value("Cost Center", {"is_group": 0})
        return frappe.get_doc({
            "doctype": "Building", "building_name": "PB " + _h(), "site": self.site.name,
            "total_capacity": 4, "company": self.company, "default_cost_center": cc,
            "is_procurement_store": 1,
        }).insert(ignore_permissions=True).name

    def test_cancel_receipt_blocked_once_stock_has_been_issued_out(self):
        """Cancelling a receipt whose goods already left the store must be refused,
        not mirrored: the reversal would drive the store negative and invent stock
        that is physically in an employee's hands. Nothing may be written on refusal."""
        from apex.habitat.doctype.accommodation_stock_ledger.accommodation_stock_ledger import (
            get_store_balance,
        )
        building = self._procurement_building()

        receipt = frappe.get_doc({
            "doctype": "Goods Receipt", "naming_series": "ACC-GRN-.YYYY.-.#####",
            "receipt_date": "2026-05-01", "intake_building": building,
            "procurement_supervisor": "Administrator",
        })
        receipt.append("items", {"item_type": "Custody Article", "item": self.article, "qty": 10})
        receipt.insert(ignore_permissions=True)
        receipt.submit()
        self.assertEqual(get_store_balance("Custody Article", self.article, building), 10.0)

        issue = frappe.get_doc({"doctype": "Custody Issue", "naming_series": "CUST-ISS-.####",
                                "issue_date": "2026-05-02", "issued_to_employee": self.emp,
                                "building": building})
        issue.append("items", {"article": self.article, "qty": 10})
        issue.insert(ignore_permissions=True)
        issue.submit()
        self.assertEqual(get_store_balance("Custody Article", self.article, building), 0.0)

        receipt.reload()
        with self.assertRaises(frappe.ValidationError):
            receipt.cancel()

        self.assertGreaterEqual(
            get_store_balance("Custody Article", self.article, building), 0.0,
            "a refused reversal must never drive the building store negative",
        )
        self.assertEqual(
            frappe.db.count("Accommodation Stock Ledger",
                            {"voucher_no": receipt.name, "reversal_of": ["is", "set"]}), 0,
            "a refused reversal must write no mirror row for the cancelled voucher",
        )
