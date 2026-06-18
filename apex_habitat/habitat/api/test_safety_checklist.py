"""Tests for the Safety Checklist API.

Covers the two whitelisted backend methods that power the Safety Checklist desk
Page (the Page UI/JS is a separate task and is not exercised here).

get_tasks_for_cadence: returns exactly the in-scope catalog tasks for a
(building, cadence) using BOTH scope modes — a task scoped to the building via
the Safety Task Building Scope child table AND an applies-to-all-buildings task
— while excluding an other-cadence task and an other-building-scoped task.

submit_round: in one transaction records a Safety Round plus one submitted
Safety Task Execution per checklist line linked back to the round, and the
round's overall_result matches the worst line status (a Poor -> Needs Attention;
a Not Done -> Fail; all Good -> Pass). A second non-reinspection submit_round for
the same (building, date, cadence) is rejected by the round's duplicate guard.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today

from apex_habitat.habitat.api.safety_checklist import (
    get_tasks_for_cadence,
    submit_round,
)
from apex_habitat.tests.factories import make_building, make_company


class TestSafetyChecklist(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        tag = self._testMethodName

        make_company()
        self.building = make_building(name=f"Checklist Bldg {tag}").name
        self.other_building = make_building(name=f"Checklist Other {tag}").name

        # Mode 1: a Weekly task that applies to every building.
        self.task_all = frappe.get_doc(
            {
                "doctype": "Safety Task Catalog",
                "task_code": f"CHK-ALL-{tag}",
                "task_title": f"All-Buildings Task {tag}",
                "task_title_en": f"All-Buildings Task EN {tag}",
                "department": "Fire Safety",
                "frequency": "Weekly",
                "priority": "High",
                "evidence_required": 1,
                "instructions": "Check all extinguishers.",
                "applicable_to_all_buildings": 1,
                "is_active": 1,
            }
        ).insert(ignore_permissions=True).name

        # Mode 2: a Weekly task scoped to THIS building only.
        self.task_scoped = frappe.get_doc(
            {
                "doctype": "Safety Task Catalog",
                "task_code": f"CHK-SCP-{tag}",
                "task_title": f"Scoped Task {tag}",
                "department": "Security",
                "frequency": "Weekly",
                "priority": "Medium",
                "applicable_to_all_buildings": 0,
                "is_active": 1,
                "applicable_buildings": [{"building": self.building}],
            }
        ).insert(ignore_permissions=True).name

        # A Weekly task scoped to a DIFFERENT building — must be excluded.
        self.task_other_building = frappe.get_doc(
            {
                "doctype": "Safety Task Catalog",
                "task_code": f"CHK-OTH-{tag}",
                "task_title": f"Other-Building Task {tag}",
                "department": "Security",
                "frequency": "Weekly",
                "priority": "Low",
                "applicable_to_all_buildings": 0,
                "is_active": 1,
                "applicable_buildings": [{"building": self.other_building}],
            }
        ).insert(ignore_permissions=True).name

        # An applies-to-all task of a DIFFERENT cadence — must be excluded for
        # the Weekly checklist.
        self.task_other_cadence = frappe.get_doc(
            {
                "doctype": "Safety Task Catalog",
                "task_code": f"CHK-CAD-{tag}",
                "task_title": f"Monthly Task {tag}",
                "department": "Maintenance",
                "frequency": "Monthly",
                "priority": "Medium",
                "applicable_to_all_buildings": 1,
                "is_active": 1,
            }
        ).insert(ignore_permissions=True).name

    # -- get_tasks_for_cadence -------------------------------------------------

    def test_get_tasks_returns_exactly_in_scope_tasks(self):
        result = get_tasks_for_cadence(self.building, "Weekly")

        self.assertEqual(result["building"], self.building)
        self.assertEqual(result["cadence"], "Weekly")

        names = {t["name"] for t in result["tasks"]}
        # Both scope modes are included.
        self.assertIn(self.task_all, names, "all-buildings task must be in scope")
        self.assertIn(self.task_scoped, names, "building-scoped task must be in scope")
        # Out-of-scope tasks are excluded.
        self.assertNotIn(
            self.task_other_building, names,
            "a task scoped to another building must be excluded",
        )
        self.assertNotIn(
            self.task_other_cadence, names,
            "a task of another cadence must be excluded",
        )
        # Exactly the two in-scope tasks (none of THIS test's out-of-scope ones).
        self.assertEqual(
            names & {self.task_all, self.task_scoped, self.task_other_building,
                     self.task_other_cadence},
            {self.task_all, self.task_scoped},
        )

    def test_get_tasks_payload_carries_render_fields(self):
        result = get_tasks_for_cadence(self.building, "Weekly")
        by_name = {t["name"]: t for t in result["tasks"]}

        row = by_name[self.task_all]
        self.assertEqual(
            row["task_title"],
            frappe.db.get_value("Safety Task Catalog", self.task_all, "task_title"),
        )
        self.assertEqual(row["task_title_en"], f"All-Buildings Task EN {self._testMethodName}")
        self.assertEqual(row["department"], "Fire Safety")
        self.assertEqual(row["priority"], "High")
        self.assertEqual(row["evidence_required"], 1)
        self.assertEqual(row["instructions"], "Check all extinguishers.")

    def test_get_tasks_other_cadence_returns_only_that_cadence(self):
        # The Monthly applies-to-all task appears for Monthly, and the Weekly
        # ones do not.
        result = get_tasks_for_cadence(self.building, "Monthly")
        names = {t["name"] for t in result["tasks"]}
        self.assertIn(self.task_other_cadence, names)
        self.assertNotIn(self.task_all, names)
        self.assertNotIn(self.task_scoped, names)

    # -- submit_round ----------------------------------------------------------

    def _lines(self, *statuses):
        # Use the in-scope tasks, cycling if more statuses than tasks.
        tasks = [self.task_all, self.task_scoped]
        return [
            {"task": tasks[i % len(tasks)], "execution_status": s}
            for i, s in enumerate(statuses)
        ]

    def _assert_round_and_executions(self, result, expected_count):
        self.assertTrue(result["ok"])
        round_name = result["safety_round"]
        self.assertTrue(round_name)
        self.assertEqual(result["count"], expected_count)

        # Exactly one Safety Round, and it is submitted.
        self.assertEqual(
            frappe.db.get_value("Safety Round", round_name, "docstatus"), 1
        )

        # N submitted Safety Task Execution rows, all linked to the round.
        steps = frappe.get_all(
            "Safety Task Execution",
            filters={"safety_round": round_name, "docstatus": 1},
            fields=["name", "building", "execution_date", "execution_status"],
        )
        self.assertEqual(len(steps), expected_count)
        for ste in steps:
            self.assertEqual(ste.building, self.building)
            self.assertEqual(str(ste.execution_date), today())
        return round_name

    def test_submit_round_all_good_is_pass(self):
        result = submit_round(self.building, "Weekly", today(), self._lines("Good", "Good"))
        self._assert_round_and_executions(result, 2)
        self.assertEqual(result["overall_result"], "Pass")

    def test_submit_round_poor_is_needs_attention(self):
        result = submit_round(self.building, "Weekly", today(), self._lines("Good", "Poor"))
        self._assert_round_and_executions(result, 2)
        self.assertEqual(result["overall_result"], "Needs Attention")

    def test_submit_round_not_done_is_fail(self):
        # Not Done outranks Poor: worst status wins -> Fail.
        result = submit_round(
            self.building, "Weekly", today(), self._lines("Poor", "Not Done")
        )
        self._assert_round_and_executions(result, 2)
        self.assertEqual(result["overall_result"], "Fail")

    def test_submit_round_links_executions_to_round(self):
        result = submit_round(self.building, "Weekly", today(), self._lines("Good"))
        round_name = self._assert_round_and_executions(result, 1)
        linked = frappe.get_all(
            "Safety Task Execution",
            filters={"safety_round": round_name},
            pluck="task",
        )
        self.assertEqual(set(linked), {self.task_all})

    def test_duplicate_non_reinspection_round_is_rejected(self):
        submit_round(self.building, "Weekly", today(), self._lines("Good"))
        # A second non-reinspection round for the same building/date/cadence is
        # blocked by the Safety Round duplicate guard.
        with self.assertRaises(frappe.ValidationError):
            submit_round(self.building, "Weekly", today(), self._lines("Good"))

    def test_reinspection_round_is_allowed(self):
        submit_round(self.building, "Weekly", today(), self._lines("Good"))
        # The same date/cadence is allowed when flagged as a re-inspection.
        result = submit_round(
            self.building, "Weekly", today(), self._lines("Good"), is_reinspection=1
        )
        self.assertTrue(result["ok"])
        self.assertEqual(
            frappe.db.get_value(
                "Safety Round", result["safety_round"], "is_reinspection"
            ),
            1,
        )
