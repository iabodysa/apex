# Copyright (c) 2026, AFMCO Support Services Co. Ltd and Contributors
# [#gi2kqa]

import frappe
from frappe.tests.utils import FrappeTestCase


class TestAccommodationStockLedger(FrappeTestCase):
    def test_insert_minimal_ledger_row(self):
        """Smoke test: a minimal valid Stock Ledger row (all mandatory fields set)
        inserts, gets a name, and deletes cleanly. The item / building Links are
        supplied as placeholders with ignore_links=True so the smoke test exercises
        the row write path without standing up the full master chain."""
        doc = frappe.get_doc({
            "doctype": "Accommodation Stock Ledger",
            "naming_series": "ACC-SLE-.YYYY.-.######",
            "posting_date": "2026-06-01",
            "item_type": "Custody Article",
            "item": "SLE-SMOKE-ITEM",
            "signed_qty": 1,
            "building": "SLE-SMOKE-BLDG",
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.assertIsNotNone(doc.name)

        frappe.delete_doc("Accommodation Stock Ledger", doc.name, force=True, ignore_permissions=True)
