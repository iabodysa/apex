# Copyright (c) 2026, AFMCO and contributors
"""Tests for the Safety Task Compliance Summary report.

Proves execute() returns the expected per-task shape over seeded, submitted
Safety Task Execution rows: the expected denominator follows the two-mode
catalog scope (all-buildings task + building-scoped task), last status is the
most recent execution, needs-attention counts Poor + Not Done, evidence
presence is detected, and an expected-but-never-executed task surfaces with a
zero executed count.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today

from apex.habitat.report.safety_task_compliance_summary.safety_task_compliance_summary import execute


class TestSafetyTaskComplianceSummary(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        tag = self._testMethodName

        self.building = frappe.get_doc(
            {
                "doctype": "Building",
                "building_name": f"SRC Bldg {tag}",
                "status": "Active",
            }
        ).insert(ignore_permissions=True).name

        # [#4b4aog]
        self.task_all = frappe.get_doc(
            {
                "doctype": "Safety Task Catalog",
                "task_code": f"SAF-ALL-{tag}",
                "task_title": f"All-Buildings Task {tag}",
                "department": "Fire Safety",
                "frequency": "Weekly",
                "priority": "High",
                "applicable_to_all_buildings": 1,
                "is_active": 1,
            }
        ).insert(ignore_permissions=True).name

        # [#m2ce7m]
        self.task_scoped = frappe.get_doc(
            {
                "doctype": "Safety Task Catalog",
                "task_code": f"SAF-SCP-{tag}",
                "task_title": f"Scoped Task {tag}",
                "department": "Security",
                "frequency": "Weekly",
                "priority": "Medium",
                "applicable_to_all_buildings": 0,
                "is_active": 1,
                "applicable_buildings": [{"building": self.building}],
            }
        ).insert(ignore_permissions=True).name

        # [#a0qvoa]
        other_building = frappe.get_doc(
            {
                "doctype": "Building",
                "building_name": f"SRC Other {tag}",
                "status": "Active",
            }
        ).insert(ignore_permissions=True).name
        self.task_other = frappe.get_doc(
            {
                "doctype": "Safety Task Catalog",
                "task_code": f"SAF-OTH-{tag}",
                "task_title": f"Other Task {tag}",
                "department": "Security",
                "frequency": "Weekly",
                "priority": "Low",
                "applicable_to_all_buildings": 0,
                "is_active": 1,
                "applicable_buildings": [{"building": other_building}],
            }
        ).insert(ignore_permissions=True).name

    def _execution(self, task, status, evidence=None):
        return frappe.get_doc(
            {
                "doctype": "Safety Task Execution",
                "building": self.building,
                "task": task,
                "execution_date": today(),
                "execution_status": status,
                "evidence_photo": evidence,
            }
        ).insert(ignore_permissions=True).submit()

    def _rows_by_task(self, data):
        return {row["task"]: row for row in data}

    def test_expected_set_uses_both_scope_modes(self):
        _columns, data = execute({"cadence": "Weekly", "building": self.building})
        by_task = self._rows_by_task(data)

        self.assertIn(self.task_all, by_task, "all-buildings task must be expected")
        self.assertIn(self.task_scoped, by_task, "building-scoped task must be expected")
        self.assertNotIn(
            self.task_other, by_task,
            "a task scoped to another building must not be in the denominator",
        )
        self.assertEqual(by_task[self.task_all]["expected"], 1)
        self.assertEqual(by_task[self.task_scoped]["expected"], 1)

    def test_per_task_shape_counts_and_last_status(self):
        # [#h94o8h]
        self._execution(self.task_all, "Good", evidence="/files/a.jpg")
        self._execution(self.task_all, "Poor")
        # [#jrpb21]
        self._execution(self.task_scoped, "Not Done")

        _columns, data = execute({"cadence": "Weekly", "building": self.building})
        by_task = self._rows_by_task(data)

        all_row = by_task[self.task_all]
        self.assertEqual(all_row["executed_count"], 2)
        self.assertEqual(all_row["last_status"], "Poor")
        self.assertEqual(all_row["needs_attention_count"], 1)
        self.assertEqual(all_row["done_count"], 1)
        self.assertEqual(all_row["has_evidence"], 1)
        self.assertEqual(all_row["task_title"], frappe.db.get_value(
            "Safety Task Catalog", self.task_all, "task_title"))

        scoped_row = by_task[self.task_scoped]
        self.assertEqual(scoped_row["executed_count"], 1)
        self.assertEqual(scoped_row["last_status"], "Not Done")
        self.assertEqual(scoped_row["needs_attention_count"], 1)
        self.assertEqual(scoped_row["has_evidence"], 0)

    def test_expected_but_unexecuted_task_has_zero_count(self):
        # [#rb1slp]
        self._execution(self.task_scoped, "Good")

        _columns, data = execute({"cadence": "Weekly", "building": self.building})
        by_task = self._rows_by_task(data)

        self.assertIn(self.task_all, by_task)
        self.assertEqual(by_task[self.task_all]["executed_count"], 0)
        self.assertEqual(by_task[self.task_all]["last_status"], "")
        self.assertEqual(by_task[self.task_all]["expected"], 1)
