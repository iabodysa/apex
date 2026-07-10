# Copyright (c) 2026, AFMCO and contributors
"""consumable_custody_expiry_watch flags held custody consumables past their
per-article lifespan and leaves in-date holdings alone.

A held position is a net-positive (item, employee) Accommodation Stock Ledger
balance; the ledger posting_date comes from the Custody Issue issue_date, so a
back-dated issue ages the holding. The over-age article must raise one
"Consumable Expired" Operations Alert; the in-date article must raise none.
"""

import frappe
from frappe.utils import add_months, today

from apex.habitat.tasks import consumable_custody_expiry_watch
from apex.tests.factories import ApexHabitatTestCase


def _h(n=12):
    return frappe.generate_hash(length=n).upper()


class TestConsumableCustodyExpiry(ApexHabitatTestCase):
    def setUp(self):
        self.company = frappe.db.get_value("Company", {}) or frappe.get_doc({
            "doctype": "Company", "company_name": "Test Co", "default_currency": "SAR",
            "country": "Saudi Arabia"}).insert(ignore_permissions=True).name
        cc = (frappe.db.get_value("Cost Center", {"is_group": 0, "company": self.company})
              or frappe.db.get_value("Cost Center", {"is_group": 0}))
        self.site = frappe.get_doc({"doctype": "Site", "site_name": _h(12)}).insert(ignore_permissions=True)
        self.building = frappe.get_doc({"doctype": "Building", "building_name": "B " + _h(),
                                        "site": self.site.name, "total_capacity": 4, "company": self.company,
                                        "default_cost_center": cc}).insert(ignore_permissions=True).name
        self.cat = frappe.db.get_value("Custody Asset Category", {}) or frappe.get_doc({
            "doctype": "Custody Asset Category", "category_name": "Cat " + _h()}).insert(ignore_permissions=True).name
        self.emp = frappe.get_doc({"doctype": "Employee", "first_name": "E " + _h(), "company": self.company,
                                   "gender": "Male", "date_of_birth": "1990-01-01",
                                   "date_of_joining": "2020-01-01"}).insert(ignore_permissions=True).name

    def _article(self, lifespan):
        return frappe.get_doc({"doctype": "Custody Article", "naming_series": "CUST-ART-.####",
                               "article_name": "Linen " + _h(), "category": self.cat,
                               "unit_of_measure": "Nos",
                               "consumable_lifespan_months": lifespan}).insert(ignore_permissions=True).name

    def _issue(self, article, issue_date, qty=2):
        # Custody Issue now rejects issuing more than the store holds; receive
        # opening stock into the building store first so the issue can draw it.
        from apex.habitat.doctype.accommodation_stock_ledger.accommodation_stock_ledger import (
            post_stock_entry,
        )
        post_stock_entry(item_type="Custody Article", item=article, qty=qty,
                         building=self.building, voucher_type="Opening Stock",
                         voucher_no="OPEN-" + _h(), posting_date=issue_date)
        i = frappe.get_doc({"doctype": "Custody Issue", "naming_series": "CUST-ISS-.####",
                            "issue_date": issue_date, "issued_to_employee": self.emp, "building": self.building})
        i.append("items", {"article": article, "qty": qty})
        i.insert(ignore_permissions=True)
        i.submit()
        return i

    def _open_consumable_alerts(self, token):
        return frappe.get_all("Operations Alert", filters={
            "alert_type": "Consumable Expired", "status": "Open",
            "message": ["like", f"%{token}%"]})

    def test_over_age_fires_in_date_does_not(self):
        # Lifespan 6 months; this holding is 10 months old -> over age.
        over = self._article(lifespan=6)
        self._issue(over, issue_date=add_months(today(), -10))
        # Lifespan 12 months; this holding is 1 month old -> in date.
        in_date = self._article(lifespan=12)
        self._issue(in_date, issue_date=add_months(today(), -1))

        consumable_custody_expiry_watch()

        over_token = f"{self.emp}:{over}"
        in_token = f"{self.emp}:{in_date}"
        self.assertEqual(len(self._open_consumable_alerts(over_token)), 1)
        self.assertEqual(len(self._open_consumable_alerts(in_token)), 0)

    def test_no_lifespan_never_fires(self):
        # consumable_lifespan_months = 0 means no expiry, even for an ancient holding.
        never = self._article(lifespan=0)
        self._issue(never, issue_date=add_months(today(), -60))

        consumable_custody_expiry_watch()

        self.assertEqual(len(self._open_consumable_alerts(f"{self.emp}:{never}")), 0)

    def test_rerun_is_idempotent(self):
        over = self._article(lifespan=3)
        self._issue(over, issue_date=add_months(today(), -12))

        consumable_custody_expiry_watch()
        consumable_custody_expiry_watch()

        self.assertEqual(len(self._open_consumable_alerts(f"{self.emp}:{over}")), 1)
