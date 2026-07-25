# Copyright (c) 2026, AFMCO and contributors
"""Tests for the Safety Open Findings report execute().

Asserts the column contract and, over a seeded submitted "Poor" Safety Task
Execution, that the finding surfaces with its status and a derived days_open of
zero (executed today). Requires a live site."""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today

from apex.habitat.report.safety_open_findings.safety_open_findings import execute

_EXPECTED_FIELDS = [
    "name",
    "execution_date",
    "building",
    "task",
    "priority",
    "execution_status",
    "executed_by",
    "linked_maintenance_request",
    "days_open",
]


class TestSafetyOpenFindings(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")

    def test_columns_contract(self):
        columns, data = execute({})
        self.assertEqual([c["fieldname"] for c in columns], _EXPECTED_FIELDS)
        self.assertIsInstance(data, list)

    def test_open_execution_surfaces_with_zero_days_open(self):
        tag = frappe.generate_hash(length=6)
        building = frappe.get_doc(
            {"doctype": "Building", "building_name": f"SOF Bldg {tag}", "status": "Active"}
        ).insert(ignore_permissions=True).name
        task = frappe.get_doc(
            {
                "doctype": "Safety Task Catalog",
                "task_code": f"SOF-{tag}",
                "task_title": f"Task {tag}",
                "department": "Fire Safety",
                "frequency": "Weekly",
                "priority": "High",
                "applicable_to_all_buildings": 1,
                "is_active": 1,
            }
        ).insert(ignore_permissions=True).name
        frappe.get_doc(
            {
                "doctype": "Safety Task Execution",
                "building": building,
                "task": task,
                "execution_date": today(),
                "execution_status": "Poor",
            }
        ).insert(ignore_permissions=True).submit()

        _columns, data = execute({"building": building})
        rows = {row["name"]: row for row in data}
        self.assertTrue(rows, "a submitted Poor execution must surface as an open finding")
        row = next(iter(rows.values()))
        self.assertEqual(row["execution_status"], "Poor")
        self.assertEqual(row["building"], building)
        self.assertEqual(row["days_open"], 0)
