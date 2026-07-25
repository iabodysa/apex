# Copyright (c) 2026, AFMCO and contributors
"""Tests for the Intercompany Movement Register report execute().

Asserts the column contract and that execute() runs end-to-end returning a data
list whose rows carry every declared field (including the derived docstatus ->
status label). Requires a live site (queries Facility Asset Movement).

The row test seeds a genuine cross-company Facility Asset Movement: on an empty
test database the per-row loop had nothing to iterate, so the row-shape and
status-label assertions never executed."""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today

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
        tag = frappe.generate_hash(length=12).upper()

        # The register's whole subject is a move BETWEEN companies, so two distinct
        # companies are the irreducible fixture: is_intercompany is derived
        # server-side from from_company != to_company and cannot be forced.
        self.company_a, self.company_b = self._two_companies(tag)

        self.building_a = self._building(f"IMR From {tag}", self.company_a)
        self.building_b = self._building(f"IMR To {tag}", self.company_b)

        self.asset = frappe.get_doc(
            {
                "doctype": "Facility Asset",
                "asset_name": f"IMR Camera {tag}",
                "asset_category": "CCTV Camera",
                "building": self.building_a,
                "responsible_supervisor": "Administrator",
            }
        ).insert(ignore_permissions=True).name

        self.gate_pass = f"GP-{tag}"
        # Intercompany Temporary (not Permanent) so the accounting acknowledgement
        # gate does not apply; release + receiving approvals are still required.
        self.movement = frappe.get_doc(
            {
                "doctype": "Facility Asset Movement",
                "movement_date": today(),
                "facility_asset": self.asset,
                "movement_category": "Intercompany Temporary",
                "to_building": self.building_b,
                "release_approved_by": "Administrator",
                "receiving_confirmed_by": "Administrator",
                "gate_pass_reference": self.gate_pass,
            }
        ).insert(ignore_permissions=True)
        self.assertEqual(
            self.movement.is_intercompany,
            1,
            "The seeded movement must be detected as intercompany, or the register "
            "filters it out and the row loop is empty again.",
        )

    @staticmethod
    def _two_companies(tag):
        """Reuse the site's existing companies, topping up to two when needed."""
        names = frappe.get_all("Company", pluck="name", limit=2)
        while len(names) < 2:
            names.append(
                frappe.get_doc(
                    {
                        "doctype": "Company",
                        "company_name": f"IMR Co {tag}-{len(names)}",
                        "default_currency": "SAR",
                        "country": "Saudi Arabia",
                    }
                ).insert(ignore_permissions=True).name
            )
        return names[0], names[1]

    @staticmethod
    def _building(name, company):
        return frappe.get_doc(
            {
                "doctype": "Building",
                "building_name": name,
                "status": "Active",
                "total_capacity": 10,
                "company": company,
            }
        ).insert(ignore_permissions=True).name

    def test_columns_contract(self):
        columns, data = execute({})
        self.assertEqual([c["fieldname"] for c in columns], _EXPECTED_FIELDS)
        self.assertIsInstance(data, list)

    def test_rows_carry_expected_keys_and_status_label(self):
        _columns, data = execute({})
        self.assertTrue(data, "The seeded intercompany movement must reach the report.")

        checked = 0
        for row in data:
            for key in _EXPECTED_FIELDS:
                self.assertIn(key, row)
            self.assertIn(row["status"], ("Draft", "Submitted", "Cancelled", ""))
            checked += 1
        self.assertEqual(
            checked, len(data), "The per-row assertions must run for every row."
        )

        seeded = [r for r in data if r["name"] == self.movement.name]
        self.assertEqual(len(seeded), 1, "The seeded movement must contribute one row.")
        self.assertEqual(seeded[0]["from_company"], self.company_a)
        self.assertEqual(seeded[0]["to_company"], self.company_b)
        self.assertEqual(seeded[0]["gate_pass_reference"], self.gate_pass)
        self.assertEqual(
            seeded[0]["status"],
            "Draft",
            "An unsubmitted movement must carry the Draft docstatus label.",
        )
