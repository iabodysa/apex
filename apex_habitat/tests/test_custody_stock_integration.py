# Copyright (c) 2026, AFMCO and contributors
"""Phase B — Custody Issue/Return post to the Accommodation Stock Ledger:
issue moves stock Store -> Employee custody (same building); return moves it
back; cancel reverses. Balance = sum(qty) where is_cancelled = 0."""

import frappe
from frappe.utils import flt
from apex_habitat.tests.test_utils import ApexHabitatTestCase


def _h(n=4):
    return frappe.generate_hash(length=n).upper()


def _bal(article, building, employee=None):
    filters = {"item": article, "building": building, "is_cancelled": 0}
    filters["employee"] = employee if employee else ["is", "not set"]
    rows = frappe.get_all("Accommodation Stock Ledger", filters=filters, fields=["qty"])
    return flt(sum(flt(r.qty) for r in rows))


class TestCustodyStockIntegration(ApexHabitatTestCase):
    def setUp(self):
        self.company = frappe.db.get_value("Company", {}) or frappe.get_doc({
            "doctype": "Company", "company_name": "Test Co", "default_currency": "SAR",
            "country": "Saudi Arabia"}).insert(ignore_permissions=True).name
        cc = frappe.db.get_value("Cost Center", {"is_group": 0, "company": self.company}) or frappe.db.get_value("Cost Center", {"is_group": 0})
        self.site = frappe.get_doc({"doctype": "Accommodation Site", "site_name": _h(6)}).insert(ignore_permissions=True)
        self.building = frappe.get_doc({"doctype": "Accommodation Building", "building_name": "B " + _h(),
                                        "site": self.site.name, "total_capacity": 4, "company": self.company,
                                        "default_cost_center": cc}).insert(ignore_permissions=True).name
        cat = frappe.db.get_value("Custody Asset Category", {}) or frappe.get_doc({
            "doctype": "Custody Asset Category", "category_name": "Cat " + _h()}).insert(ignore_permissions=True).name
        self.article = frappe.get_doc({"doctype": "Custody Article", "naming_series": "ART-.####",
                                       "article_name": "Item " + _h(), "category": cat,
                                       "unit_of_measure": "Nos"}).insert(ignore_permissions=True).name
        self.emp = frappe.get_doc({"doctype": "Employee", "first_name": "E " + _h(), "company": self.company,
                                   "gender": "Male", "date_of_birth": "1990-01-01", "date_of_joining": "2020-01-01"}).insert(ignore_permissions=True).name

    def _issue(self, qty=5):
        i = frappe.get_doc({"doctype": "Custody Issue", "naming_series": "CUST-ISS-.####",
                            "issue_date": "2026-05-01", "issued_to_employee": self.emp, "building": self.building})
        i.append("items", {"article": self.article, "qty": qty})
        i.insert(ignore_permissions=True)
        i.submit()
        return i

    def test_issue_moves_to_custody_then_return_to_store(self):
        issue = self._issue(5)
        # after issue: employee custody +5, store -5 (net building 0)
        self.assertEqual(_bal(self.article, self.building, self.emp), 5.0)
        self.assertEqual(_bal(self.article, self.building, None), -5.0)

        ret = frappe.get_doc({"doctype": "Custody Return", "naming_series": "CUST-RET-.####",
                              "return_date": "2026-05-10", "custody_issue": issue.name,
                              "returned_by_employee": self.emp, "building": self.building})
        ret.append("items", {"article": self.article, "qty": 5})
        ret.insert(ignore_permissions=True)
        ret.submit()
        # after return: employee custody back to 0, store back to 0
        self.assertEqual(_bal(self.article, self.building, self.emp), 0.0)
        self.assertEqual(_bal(self.article, self.building, None), 0.0)

    def test_cancel_issue_reverses_stock(self):
        from apex_habitat.habitat.doctype.accommodation_stock_ledger.accommodation_stock_ledger import has_stock_entries
        issue = self._issue(3)
        self.assertTrue(has_stock_entries("Custody Issue", issue.name))
        issue.reload()
        issue.cancel()
        self.assertFalse(has_stock_entries("Custody Issue", issue.name))
        self.assertEqual(_bal(self.article, self.building, self.emp), 0.0)
