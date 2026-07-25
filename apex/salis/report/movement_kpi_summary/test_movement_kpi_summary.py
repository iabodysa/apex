# Copyright (c) 2026, AFMCO and contributors
"""Tests for the Movement KPI Summary report execute().

The roll-up always emits a fixed set of KPI rows (kpi / value / note), each
metric defensive about whether its source DocType is installed, plus exactly one
computed Trip Fulfilment Rate percentage row. Requires a live site."""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.salis.report.movement_kpi_summary.movement_kpi_summary import execute

_EXPECTED_FIELDS = ["kpi", "value", "note"]


class TestMovementKpiSummary(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")

    def test_columns_contract(self):
        columns, _data = execute({})
        self.assertEqual([c["fieldname"] for c in columns], _EXPECTED_FIELDS)

    def test_rollup_is_deterministic_and_has_one_percentage_row(self):
        _columns, data = execute({})
        self.assertEqual(len(data), 10)
        for row in data:
            self.assertEqual(set(row.keys()), {"kpi", "value", "note"})
        pct_rows = [row for row in data if str(row["value"]).endswith("%")]
        self.assertEqual(len(pct_rows), 1)
