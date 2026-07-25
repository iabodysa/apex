# Copyright (c) 2026, AFMCO and contributors
"""Tests for the Cost by Dimension report execute().

Asserts the column contract and that execute() runs the frappe.qb aggregation
end-to-end returning a data list whose rows carry every declared field. Requires
a live site (aggregates the Accommodation Ledger)."""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.habitat.report.cost_by_dimension.cost_by_dimension import execute, get_columns

_EXPECTED_FIELDS = ["company", "building", "project", "entries", "total_cost"]


class TestCostByDimension(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")

    def test_columns_contract(self):
        self.assertEqual([c["fieldname"] for c in get_columns()], _EXPECTED_FIELDS)

    def test_execute_returns_columns_and_data_list(self):
        columns, data = execute({})
        self.assertEqual([c["fieldname"] for c in columns], _EXPECTED_FIELDS)
        self.assertIsInstance(data, list)
        for row in data:
            for key in _EXPECTED_FIELDS:
                self.assertIn(key, row)
