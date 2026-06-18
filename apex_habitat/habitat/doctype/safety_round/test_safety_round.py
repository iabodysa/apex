"""Tests for the Safety Round controller.

Proves the duplicate guard fires for a repeated first round and that a marked
re-inspection is allowed as a second round, and that on_submit derives the
overall result from the linked Safety Task Execution statuses (worst wins):
a Not Done yields Fail, a Poor yields Needs Attention, all-good yields Pass.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today


class TestSafetyRound(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        tag = self._testMethodName

        # A building to round, and a catalog task to execute against it.
        self.building = frappe.get_doc(
            {
                "doctype": "Accommodation Building",
                "building_name": f"Round Bldg {tag}",
                "status": "Active",
            }
        ).insert(ignore_permissions=True).name

        self.task = frappe.get_doc(
            {
                "doctype": "Safety Task Catalog",
                "task_code": f"SAF-RND-{tag}",
                "task_title": f"Round Task {tag}",
                "department": "Fire Safety",
                "frequency": "Weekly",
                "priority": "High",
                "applicable_to_all_buildings": 1,
                "is_active": 1,
            }
        ).insert(ignore_permissions=True).name

    def _round(self, **overrides):
        data = {
            "doctype": "Safety Round",
            "building": self.building,
            "round_date": today(),
            "cadence": "Weekly",
        }
        data.update(overrides)
        return frappe.get_doc(data).insert(ignore_permissions=True)

    def _execution(self, safety_round, status):
        return frappe.get_doc(
            {
                "doctype": "Safety Task Execution",
                "building": self.building,
                "task": self.task,
                "execution_date": today(),
                "execution_status": status,
                "safety_round": safety_round,
            }
        ).insert(ignore_permissions=True)

    def test_duplicate_first_round_is_blocked(self):
        self._round()
        with self.assertRaises(frappe.ValidationError):
            self._round()

    def test_reinspection_second_round_is_allowed(self):
        self._round()
        # An explicit re-inspection for the same building/date/cadence is allowed.
        second = self._round(is_reinspection=1)
        self.assertTrue(second.name, "a marked re-inspection must be accepted")

    def test_overall_result_fail_when_a_task_not_done(self):
        rnd = self._round()
        self._execution(rnd.name, "Good").submit()
        self._execution(rnd.name, "Not Done").submit()
        rnd.submit()
        rnd.reload()
        self.assertEqual(rnd.overall_result, "Fail")

    def test_overall_result_needs_attention_when_a_task_poor(self):
        rnd = self._round()
        self._execution(rnd.name, "Good").submit()
        self._execution(rnd.name, "Poor").submit()
        rnd.submit()
        rnd.reload()
        self.assertEqual(rnd.overall_result, "Needs Attention")

    def test_overall_result_pass_when_all_good(self):
        rnd = self._round()
        self._execution(rnd.name, "Excellent").submit()
        self._execution(rnd.name, "Good").submit()
        rnd.submit()
        rnd.reload()
        self.assertEqual(rnd.overall_result, "Pass")
