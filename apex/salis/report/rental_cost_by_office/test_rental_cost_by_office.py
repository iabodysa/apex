# Copyright (c) 2026, AFMCO and contributors
"""Tests for the Rental Cost by Office report's per-office accrual aggregation.

Proves the bucket-by-office grouping actually sums what its columns claim: total
accrued, the settled/outstanding split, and the distinct-vehicle count (not the
row count) -- against fixtures this test owns and filters down to by
``rental_office``, so it is immune to any other Rental Accrual Ledger data
already on the site.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from apex.salis.report.rental_cost_by_office.rental_cost_by_office import execute
from apex.tests.factories import make_vehicle


class TestRentalCostByOffice(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        tag = frappe.generate_hash(length=8).upper()
        self.office = frappe.get_doc(
            {"doctype": "Rental Office", "office_name": f"A564 RCBO Office {tag}"}
        ).insert(ignore_permissions=True).name
        self.vehicle_a = make_vehicle(f"A564-RCBO-A-{tag}")
        self.vehicle_b = make_vehicle(f"A564-RCBO-B-{tag}")

        self._rows = []
        for vehicle, amount, settled in (
            (self.vehicle_a, 100.0, 1),
            (self.vehicle_a, 50.0, 0),
            (self.vehicle_b, 25.0, 0),
        ):
            row = frappe.get_doc(
                {
                    "doctype": "Rental Accrual Ledger",
                    "vehicle": vehicle,
                    "rental_office": self.office,
                    "accrual_date": "2026-06-01",
                    "amount": amount,
                    "settled": settled,
                }
            ).insert(ignore_permissions=True)
            self._rows.append(row.name)
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        for name in self._rows:
            frappe.delete_doc("Rental Accrual Ledger", name, force=True, ignore_permissions=True)

    def _office_row(self, filters=None):
        filters = dict(filters or {})
        filters["rental_office"] = self.office
        columns, data, *_rest = execute(filters)
        matches = [r for r in data if r["rental_office"] == self.office]
        self.assertEqual(len(matches), 1, "one aggregated row per office")
        return columns, matches[0]

    def test_total_accrued_sums_every_row_for_the_office(self):
        _columns, row = self._office_row()
        self.assertEqual(flt(row["total_accrued"]), 175.0)

    def test_settled_and_outstanding_split_by_the_settled_flag(self):
        _columns, row = self._office_row()
        self.assertEqual(flt(row["settled_amount"]), 100.0)
        self.assertEqual(flt(row["outstanding_amount"]), 75.0)

    def test_vehicles_counts_distinct_vehicles_not_ledger_rows(self):
        _columns, row = self._office_row()
        self.assertEqual(row["vehicles"], 2, "two distinct vehicles across three rows")
        self.assertEqual(row["row_count"], 3)

    def test_filtering_by_a_different_office_excludes_these_rows(self):
        _columns, data, *_rest = execute({"rental_office": "Definitely Not A Real Office"})
        self.assertFalse(any(r["rental_office"] == self.office for r in data))
