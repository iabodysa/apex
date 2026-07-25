# Copyright (c) 2026, AFMCO and contributors
"""Tests for the Intercompany Movement Register report execute().

Asserts the column contract and that execute() runs end-to-end returning a data
list whose rows carry every declared field (including the derived docstatus ->
status label). Requires a live site (queries Facility Asset Movement)."""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.habitat.report.intercompany_movement_register.intercompany_movement_register import (
    execute,
)

_EXPECTED_FIELDS = [
    "name",
    "movement_date",
    "movement_category",
    "facility_asset",
    "from_building",
    "from_company",
    "to_building",
    "to_company",
    "release_approved_by",
    "receiving_confirmed_by",
    "accounting_acknowledged",
    "gate_pass_reference",
    "status",
]


class TestIntercompanyMovementRegister(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")

    def test_columns_contract(self):
        columns, data = execute({})
        self.assertEqual([c["fieldname"] for c in columns], _EXPECTED_FIELDS)
        self.assertIsInstance(data, list)

    def test_rows_carry_expected_keys_and_status_label(self):
        _columns, data = execute({})
        for row in data:
            for key in _EXPECTED_FIELDS:
                self.assertIn(key, row)
            self.assertIn(row["status"], ("Draft", "Submitted", "Cancelled", ""))
