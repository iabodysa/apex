# Copyright (c) 2026, AFMCO and contributors
"""Tests for the Fuel Claim Register report execute().

Asserts the column contract and that execute() runs end-to-end returning a data
list whose rows carry every declared field. Requires a live site (queries Fuel
Claim)."""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.salis.report.fuel_claim_register.fuel_claim_register import execute

_EXPECTED_FIELDS = [
    "name",
    "project",
    "vehicle",
    "period_month",
    "claimed_litres",
    "consumed_litres",
    "variance_litres",
    "status",
]


class TestFuelClaimRegister(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")

    def test_columns_contract(self):
        columns, data = execute({})
        self.assertEqual([c["fieldname"] for c in columns], _EXPECTED_FIELDS)
        self.assertIsInstance(data, list)

    def test_rows_carry_expected_keys(self):
        _columns, data = execute({})
        for row in data:
            for key in _EXPECTED_FIELDS:
                self.assertIn(key, row)
