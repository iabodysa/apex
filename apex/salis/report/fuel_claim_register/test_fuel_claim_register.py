# Copyright (c) 2026, AFMCO and contributors
"""Tests for the Fuel Claim Register report execute().

Asserts the column contract and that execute() runs end-to-end returning a data
list whose rows carry every declared field. Requires a live site (queries Fuel
Claim).

The row test seeds a draft claim: on an empty test database the per-row loop had
nothing to iterate, so the row-shape assertion never executed and the
claimed/consumed/variance triple the register exists to show went unproven. The
vehicle and the project are read rather than built — only the claim is the subject.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.salis.report.fuel_claim_register.fuel_claim_register import execute

# Project is deliberately NOT a dependency. ERPNext's Project fixture is not idempotent —
# its autoname mints a new name while project_name carries a unique index, so a second
# build attempt collides instead of being skipped. The claim only needs a project id, so
# the one already on the site is read rather than rebuilt.
test_dependencies = ["Salis Vehicle"]

PLATE = "_T ABC 1001"

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
        self.project = frappe.db.get_value("Project", {"project_name": "_Test Project"})
        self.vehicle = frappe.db.get_value("Salis Vehicle", {"plate_number": PLATE}, "name")
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
        columns, data, *_rest = execute({})
        self.assertEqual([c["fieldname"] for c in columns], _EXPECTED_FIELDS)
        self.assertIsInstance(data, list)

    def test_rows_carry_expected_keys(self):
        _columns, data, *_rest = execute({})
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
        _columns, data, *_rest = execute({"project": self.project})
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
