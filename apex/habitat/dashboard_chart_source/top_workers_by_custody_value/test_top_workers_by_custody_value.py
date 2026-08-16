# Copyright (c) 2026, afmcoltd
"""Contract test for the Top Workers by Custody Value chart source.

A dashboard chart source must return ``{"labels": [...], "datasets": [...]}``
with ``labels`` and each dataset's ``values`` the SAME length — a ragged chart
source renders blank. Built from real Accommodation Stock Ledger rows via
``goods_receipt``/custody-issue so the underlying aggregate query
(``get_top_custody_holders_by_value``) is exercised end to end, not stubbed.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.habitat.dashboard_chart_source.top_workers_by_custody_value.top_workers_by_custody_value import (
    get,
)
from apex.tests._helpers import as_user
from apex.tests.factories import make_building, make_company, make_goods_receipt

# Shipped test fixtures (apex.tests.factories docstring / card): stable
# across every bench, never a per-run generated name.
ARTICLE = "_T-Custody Article-00001"
EMPLOYEE = "_T-Employee-00001"


class TestTopWorkersByCustodyValueChartSource(FrappeTestCase):
    def test_empty_ledger_returns_well_shaped_empty_chart(self):
        # Isolated only in the sense that no ledger rows are created here; whatever
        # the site already carries still participates, so this asserts the SHAPE
        # of the return, not that it is literally empty.
        # no_cache=1 skips the cache_source wrapper's chart-name resolution, which
        # otherwise requires a real Dashboard Chart record this suite has no need of.
        result = get(no_cache=1)
        self.assertIn("labels", result)
        self.assertIn("datasets", result)
        self.assertEqual(result["type"], "bar")
        self.assertEqual(len(result["datasets"]), 1)
        self.assertEqual(len(result["labels"]), len(result["datasets"][0]["values"]))

    def test_labels_and_values_stay_aligned_with_real_ledger_rows(self):
        # Stock must be ON HAND before it can be issued to an employee — bring it
        # into a store-flagged building first, exactly like the custody fixtures do.
        make_company()
        building = make_building(
            name="A564 Custody Chart Building", is_procurement_store=1, store_is_active=1
        )
        make_goods_receipt(building.name, ARTICLE, "Administrator", qty=5)

        issue = frappe.get_doc(
            {
                "doctype": "Custody Issue",
                "naming_series": "CUST-ISS-.YYYY.-.####",
                "issue_date": frappe.utils.today(),
                "building": building.name,
                "issued_to_employee": EMPLOYEE,
                "items": [{"article": ARTICLE, "qty": 1}],
            }
        )
        issue.insert(ignore_permissions=True)
        issue.submit()
        self.addCleanup(lambda: (issue.cancel(), frappe.delete_doc(
            "Custody Issue", issue.name, force=True, ignore_permissions=True
        )))

        result = get(no_cache=1)
        self.assertEqual(len(result["labels"]), len(result["datasets"][0]["values"]))
        self.assertGreaterEqual(len(result["labels"]), 1)
        self.assertIn(
            frappe.db.get_value("Employee", EMPLOYEE, "employee_name"), result["labels"]
        )

    def test_denies_a_caller_without_read_on_accommodation_stock_ledger(self):
        with as_user("Guest"):
            with self.assertRaises(frappe.PermissionError):
                get(no_cache=1)
