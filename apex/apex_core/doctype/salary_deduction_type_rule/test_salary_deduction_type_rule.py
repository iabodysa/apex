# Copyright (c) 2026, AFMCO and contributors
"""Tests for the Salary Deduction Type Rule child row.

Skeleton child (no standalone lifecycle); it is exercised in its real parent
context — the Salary Deduction Policy single's ``type_rules`` table — via an ORM
round-trip. The row is kept disabled so it round-trips without tripping the
parent's enabled-rule guards (which require a Salary Component). Requires a live
site."""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase


class TestSalaryDeductionTypeRule(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        # The policy is a Single holding deployment config; this test wipes its
        # type_rules, so snapshot the rows and register the restore BEFORE mutating
        # (FrappeTestCase rolls back once per CLASS, not per test).
        policy = frappe.get_single("Salary Deduction Policy")
        self._rows = [
            {
                "deduction_type": row.deduction_type,
                "enabled": row.enabled,
                "cap_amount_per_event": row.cap_amount_per_event,
                "max_percent_of_salary": row.max_percent_of_salary,
                "schedule": row.schedule,
                "trigger_event": row.trigger_event,
            }
            for row in policy.type_rules
        ]
        self.addCleanup(self._restore_policy)

    def _restore_policy(self):
        policy = frappe.get_single("Salary Deduction Policy")
        policy.set("type_rules", self._rows)
        policy.save(ignore_permissions=True)

    def test_type_rule_row_round_trips(self):
        policy = frappe.get_single("Salary Deduction Policy")
        policy.set("type_rules", [])
        policy.append(
            "type_rules",
            {
                "deduction_type": "Damage",
                "enabled": 0,
                "cap_amount_per_event": 500,
                "max_percent_of_salary": 10,
                "schedule": "Installments",
                "trigger_event": "On Submit",
            },
        )
        policy.save(ignore_permissions=True)

        reloaded = frappe.get_single("Salary Deduction Policy")
        rows = {r.deduction_type: r for r in reloaded.type_rules}
        self.assertIn("Damage", rows)
        row = rows["Damage"]
        self.assertEqual(row.enabled, 0)
        self.assertEqual(row.cap_amount_per_event, 500)
        self.assertEqual(row.schedule, "Installments")
        self.assertEqual(row.trigger_event, "On Submit")
