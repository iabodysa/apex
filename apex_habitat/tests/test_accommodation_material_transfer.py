# Copyright (c) 2026, AFMCO and contributors
"""Phase C — Accommodation Material Transfer moves stock between two building
stores on the Accommodation Stock Ledger: submit ships out of the source store
(In Transit), mark_received lands it in the destination store (Received), and
cancel reverses every posted leg. Availability is enforced at submit."""

import frappe
from apex_habitat.tests.test_utils import ApexHabitatTestCase
from apex_habitat.habitat.doctype.accommodation_stock_ledger.accommodation_stock_ledger import (
    post_stock_entry, get_store_balance,
)
from apex_habitat.habitat.doctype.accommodation_material_transfer.accommodation_material_transfer import (
    mark_received,
)


def _h(n=4):
    return frappe.generate_hash(length=n).upper()


class TestAccommodationMaterialTransfer(ApexHabitatTestCase):
    def setUp(self):
        self.company = frappe.db.get_value("Company", {}) or frappe.get_doc({
            "doctype": "Company", "company_name": "Test Co", "default_currency": "SAR",
            "country": "Saudi Arabia"}).insert(ignore_permissions=True).name
        cc = frappe.db.get_value("Cost Center", {"is_group": 0, "company": self.company}) or frappe.db.get_value("Cost Center", {"is_group": 0})
        self.site = frappe.get_doc({"doctype": "Accommodation Site", "site_name": _h(6)}).insert(ignore_permissions=True)
        self.b1 = self._building(cc)
        self.b2 = self._building(cc)
        cat = frappe.db.get_value("Custody Asset Category", {}) or frappe.get_doc({
            "doctype": "Custody Asset Category", "category_name": "Cat " + _h()}).insert(ignore_permissions=True).name
        self.article = frappe.get_doc({"doctype": "Custody Article", "naming_series": "ART-.####",
                                       "article_name": "Item " + _h(), "category": cat,
                                       "unit_of_measure": "Nos"}).insert(ignore_permissions=True).name

    def _building(self, cc):
        return frappe.get_doc({"doctype": "Accommodation Building", "building_name": "B " + _h(),
                               "site": self.site.name, "total_capacity": 4, "company": self.company,
                               "default_cost_center": cc}).insert(ignore_permissions=True).name

    def _seed_store(self, building, qty):
        # Seed opening stock into a building store via a generic voucher.
        post_stock_entry(item_type="Custody Article", item=self.article, qty=qty,
                         building=building, voucher_type="Opening Stock", voucher_no="OPEN-" + _h())

    def _transfer(self, qty=4):
        t = frappe.get_doc({"doctype": "Accommodation Material Transfer", "naming_series": "ACC-MTR-.YYYY.-.######",
                            "transfer_date": "2026-05-01", "from_building": self.b1, "to_building": self.b2})
        t.append("items", {"item_type": "Custody Article", "item": self.article, "qty": qty})
        t.insert(ignore_permissions=True)
        t.submit()
        return t

    def test_ship_then_receive_moves_between_stores(self):
        self._seed_store(self.b1, 10)
        t = self._transfer(4)
        # In transit: source down to 6, destination still 0 (qty in transit)
        self.assertEqual(t.status, "In Transit")
        self.assertEqual(get_store_balance("Custody Article", self.article, self.b1), 6.0)
        self.assertEqual(get_store_balance("Custody Article", self.article, self.b2), 0.0)

        mark_received(t.name, "2026-05-03")
        t.reload()
        self.assertEqual(t.status, "Received")
        self.assertEqual(get_store_balance("Custody Article", self.article, self.b1), 6.0)
        self.assertEqual(get_store_balance("Custody Article", self.article, self.b2), 4.0)

    def test_insufficient_source_stock_blocks_submit(self):
        self._seed_store(self.b1, 2)
        with self.assertRaises(frappe.ValidationError):
            self._transfer(5)

    def test_cancel_reverses_both_legs(self):
        self._seed_store(self.b1, 10)
        t = self._transfer(4)
        mark_received(t.name, "2026-05-03")
        t.reload()
        t.cancel()
        self.assertEqual(get_store_balance("Custody Article", self.article, self.b1), 10.0)
        self.assertEqual(get_store_balance("Custody Article", self.article, self.b2), 0.0)
