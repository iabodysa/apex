# Copyright (c) 2026, AFMCO and contributors
"""What the kiosk calls "in the store" must be what the ledger calls the store leg.

``get_store_balance`` identifies the building's own stock as the row with NO party
(accommodation_stock_ledger.py:202-204). The kiosk built its own version of that sum and
identified the store leg by ``employee IS NULL`` instead — and a Temporary Worker's custody
row is written with ``party`` set and ``employee`` deliberately left NULL
(``_resolve_holder``), so every article in a temporary worker's hands was counted as
available on the shelf. The storekeeper is then offered stock that is already issued, and
the issue is refused at the ledger with a message about a balance the screen never showed.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.habitat.api.custody_kiosk import _article_store_balance, get_kiosk_catalog
from apex.habitat.doctype.accommodation_stock_ledger.accommodation_stock_ledger import (
    get_store_balance,
    post_stock_entry,
)

test_dependencies = ["Bed", "Employee", "Custody Article"]

BUILDING = "_Test Building"
ARTICLE = "_T-Custody Article-00005"


class TestKioskStoreBalanceExcludesWorkerCustody(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self.worker = frappe.get_doc({
            "doctype": "Temporary Worker",
            "worker_name": "TW-" + frappe.generate_hash(length=10).upper(),
            "passport_number": "P" + frappe.generate_hash(length=10).upper(),
            "status": "Active",
        }).insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)

    def _catalog_balance(self):
        catalog = get_kiosk_catalog(building=BUILDING)
        for row in catalog["articles"]:
            if row["article"] == ARTICLE:
                return row["store_balance"]
        self.fail(f"{ARTICLE} is not in the kiosk catalog")

    def test_stock_in_a_temporary_workers_hands_is_not_offered_as_shelf_stock(self):
        voucher = "_T-KIOSK-" + frappe.generate_hash(length=8)
        post_stock_entry(
            item_type="Custody Article", item=ARTICLE, qty=3, building=BUILDING,
            voucher_type="Goods Receipt", voucher_no=voucher,
        )
        before_catalog = self._catalog_balance()
        before_probe = _article_store_balance(ARTICLE, BUILDING)

        post_stock_entry(
            item_type="Custody Article", item=ARTICLE, qty=-3, building=BUILDING,
            voucher_type="Custody Issue", voucher_no=voucher,
        )
        post_stock_entry(
            item_type="Custody Article", item=ARTICLE, qty=3, building=BUILDING,
            party_type="Temporary Worker", party=self.worker.name,
            voucher_type="Custody Issue", voucher_no=voucher,
        )

        self.assertEqual(
            self._catalog_balance(), before_catalog - 3,
            "the catalog still counts a temporary worker's custody as shelf stock",
        )
        self.assertEqual(
            _article_store_balance(ARTICLE, BUILDING), before_probe - 3,
            "the scan probe still counts a temporary worker's custody as shelf stock",
        )

    def test_the_kiosk_agrees_with_the_ledgers_own_store_balance(self):
        """One definition of "the store", not two — the ledger's."""
        self.assertEqual(
            self._catalog_balance(),
            get_store_balance("Custody Article", ARTICLE, BUILDING),
        )
        self.assertEqual(
            _article_store_balance(ARTICLE, BUILDING),
            get_store_balance("Custody Article", ARTICLE, BUILDING),
        )
