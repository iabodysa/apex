# Copyright (c) 2026, AFMCO and contributors
"""Tests for the Audit Remediation Status report execute().

Asserts the column contract and that execute() runs end-to-end returning a data
list whose rows carry every declared field (including the derived ``overdue``
flag). Requires a live site (queries Audit Remediation Item)."""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

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

    def test_columns_contract(self):
        columns, data = execute({})
        self.assertEqual([c["fieldname"] for c in columns], _EXPECTED_FIELDS)
        self.assertIsInstance(data, list)

    def test_rows_carry_expected_keys_and_binary_overdue(self):
        _columns, data = execute({})
        for row in data:
            for key in _EXPECTED_FIELDS:
                self.assertIn(key, row)
            self.assertIn(row["overdue"], ("Yes", "No"))
