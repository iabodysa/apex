# Copyright (c) 2026, AFMCO and contributors
"""Tests for the Fuel Claim Register report execute().

Asserts the column contract and that execute() runs end-to-end returning a data
list whose rows carry every declared field. Requires a live site (queries Fuel
Claim).

The row test seeds a draft claim: on an empty test database the per-row loop had
nothing to iterate, so the row-shape assertion never executed and the
claimed/consumed/variance triple the register exists to show went unproven."""

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

_CLAIMED_LITRES = 50.0


class TestFuelClaimRegister(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        tag = frappe.generate_hash(length=12).upper()

        self.project = frappe.get_doc(
            {"doctype": "Project", "project_name": f"FCR Project {tag}"}
        ).insert(ignore_permissions=True).name
        self.vehicle = frappe.get_doc(
            {
                "doctype": "Salis Vehicle",
                "plate_number": f"FCR-{tag}",
                "status": "Active",
            }
        ).insert(ignore_permissions=True).name
        self.claim = frappe.get_doc(
            {
                "doctype": "Fuel Claim",
                "project": self.project,
                "vehicle": self.vehicle,
                "period_month": "2026-05",
                "claimed_litres": _CLAIMED_LITRES,
                "status": "Draft",
            }
        ).insert(ignore_permissions=True).name

    def test_columns_contract(self):
        columns, data = execute({})
        self.assertEqual([c["fieldname"] for c in columns], _EXPECTED_FIELDS)
        self.assertIsInstance(data, list)

    def test_rows_carry_expected_keys(self):
        _columns, data = execute({})
        self.assertTrue(data, "The seeded fuel claim must reach the report.")

        checked = 0
        for row in data:
            for key in _EXPECTED_FIELDS:
                self.assertIn(key, row)
            checked += 1
        self.assertEqual(
            checked, len(data), "The per-row assertions must run for every row."
        )

    def test_seeded_claim_reports_its_variance_against_an_empty_ledger(self):
        _columns, data = execute({"project": self.project})
        seeded = [row for row in data if row["name"] == self.claim]
        self.assertEqual(len(seeded), 1, "The seeded claim must contribute one row.")
        self.assertEqual(seeded[0]["vehicle"], self.vehicle)
        self.assertEqual(seeded[0]["period_month"], "2026-05")
        self.assertEqual(seeded[0]["claimed_litres"], _CLAIMED_LITRES)
        # No Fuel Consumption Ledger rows for this vehicle/period, so the controller
        # derives consumed 0 and the whole claim shows up as variance.
        self.assertEqual(seeded[0]["consumed_litres"], 0)
        self.assertEqual(seeded[0]["variance_litres"], _CLAIMED_LITRES)
        self.assertEqual(seeded[0]["status"], "Draft")
