# Copyright (c) 2026, AFMCO and contributors
"""Tests for the Cost by Dimension report execute().

Asserts the column contract and that execute() runs the frappe.qb aggregation
end-to-end returning a data list whose rows carry every declared field. Requires
a live site (aggregates the Accommodation Ledger).

The row test seeds two Operational Memo ledger rows under one company/building/
project: on an empty test database the per-row loop had nothing to iterate, so
the row-shape assertion never executed and the aggregation itself went unproven."""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import getdate

from apex.habitat.report.cost_by_dimension.cost_by_dimension import execute, get_columns

_EXPECTED_FIELDS = ["company", "building", "project", "entries", "total_cost"]

_SHARE = 100.0


class TestCostByDimension(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        tag = frappe.generate_hash(length=12).upper()

        self.company = frappe.db.get_value("Company", {}) or frappe.get_doc(
            {
                "doctype": "Company",
                "company_name": f"CBD Co {tag}",
                "default_currency": "SAR",
                "country": "Saudi Arabia",
            }
        ).insert(ignore_permissions=True).name
        self.building = frappe.get_doc(
            {
                "doctype": "Building",
                "building_name": f"CBD Bldg {tag}",
                "status": "Active",
                "total_capacity": 10,
                "company": self.company,
            }
        ).insert(ignore_permissions=True).name
        self.project = frappe.get_doc(
            {"doctype": "Project", "project_name": f"CBD Project {tag}"}
        ).insert(ignore_permissions=True).name

        # Two memo rows on one dimension tuple, so the aggregation has something to
        # count and sum rather than collapsing to an empty result.
        for slot in ("A", "B"):
            frappe.get_doc(
                {
                    "doctype": "Accommodation Ledger",
                    "company": self.company,
                    "posting_date": getdate(),
                    "building": self.building,
                    "project": self.project,
                    "ledger_type": "Other",
                    "posting_mode": "Operational Memo",
                    "employee_daily_share": _SHARE,
                    "total_site_cost": _SHARE,
                    "source_name": f"CBD-{tag}-{slot}",
                }
            ).insert(ignore_permissions=True)

    def test_columns_contract(self):
        self.assertEqual([c["fieldname"] for c in get_columns()], _EXPECTED_FIELDS)

    def test_execute_returns_columns_and_data_list(self):
        columns, data = execute({})
        self.assertEqual([c["fieldname"] for c in columns], _EXPECTED_FIELDS)
        self.assertIsInstance(data, list)
        self.assertTrue(data, "The seeded ledger rows must reach the report.")

        checked = 0
        for row in data:
            for key in _EXPECTED_FIELDS:
                self.assertIn(key, row)
            checked += 1
        self.assertEqual(
            checked, len(data), "The per-row assertions must run for every row."
        )

    def test_rows_are_grouped_and_summed_per_dimension_tuple(self):
        _columns, data = execute({"building": self.building})
        seeded = [
            r
            for r in data
            if r["building"] == self.building and r["project"] == self.project
        ]
        self.assertEqual(
            len(seeded),
            1,
            "Both memo rows share one company/building/project tuple, so they must "
            "collapse into a single grouped row.",
        )
        self.assertEqual(seeded[0]["entries"], 2)
        self.assertEqual(float(seeded[0]["total_cost"]), 2 * _SHARE)
