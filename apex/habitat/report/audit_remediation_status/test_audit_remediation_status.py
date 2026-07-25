# Copyright (c) 2026, AFMCO and contributors
"""Tests for the Audit Remediation Status report execute().

Asserts the column contract and that execute() runs end-to-end returning a data
list whose rows carry every declared field (including the derived ``overdue``
flag). Requires a live site (queries Audit Remediation Item).

The row test seeds its own Audit Remediation Plan with one overdue remediation
item: on an empty test database the per-row loop had nothing to iterate, so the
row-shape and ``overdue`` assertions never executed."""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today

from apex.habitat.report.audit_remediation_status.audit_remediation_status import execute

_EXPECTED_FIELDS = [
    "plan",
    "remediation_action",
    "owner_role",
    "owner_user",
    "status",
    "due_date",
    "completion_date",
    "overdue",
]


class TestAuditRemediationStatus(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        tag = frappe.generate_hash(length=12).upper()
        project = frappe.get_doc(
            {"doctype": "Project", "project_name": f"ARS Project {tag}"}
        ).insert(ignore_permissions=True).name
        # One plan carrying a single past-due, uncompleted action, so the report has
        # a row AND the derived overdue flag has a determinate value.
        self.action = f"Repair the fire door on level {tag}"
        self.plan = frappe.get_doc(
            {
                "doctype": "Audit Remediation Plan",
                "client_project": project,
                "audit_received_date": add_days(today(), -30),
                "remediation_deadline": add_days(today(), -1),
                "remediation_items": [
                    {
                        "finding_description": "Fire door does not self-close.",
                        "remediation_action": self.action,
                        "due_date": add_days(today(), -7),
                        "status": "Open",
                    }
                ],
            }
        ).insert(ignore_permissions=True).name

    def test_columns_contract(self):
        columns, data = execute({})
        self.assertEqual([c["fieldname"] for c in columns], _EXPECTED_FIELDS)
        self.assertIsInstance(data, list)

    def test_rows_carry_expected_keys_and_binary_overdue(self):
        _columns, data = execute({})
        self.assertTrue(data, "The seeded remediation item must reach the report.")

        checked = 0
        for row in data:
            for key in _EXPECTED_FIELDS:
                self.assertIn(key, row)
            self.assertIn(row["overdue"], ("Yes", "No"))
            checked += 1
        self.assertEqual(
            checked, len(data), "The per-row assertions must run for every row."
        )

        seeded = [r for r in data if r["plan"] == self.plan]
        self.assertEqual(len(seeded), 1, "The seeded plan must contribute one row.")
        self.assertEqual(seeded[0]["remediation_action"], self.action)
        self.assertEqual(
            seeded[0]["overdue"],
            "Yes",
            "A past-due, uncompleted, unverified action must be flagged overdue.",
        )
