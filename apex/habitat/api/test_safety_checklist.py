# Copyright (c) 2026, AFMCO and contributors
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

get_due_cadences: returns only the cadences with no submitted round in the
current period (today / this ISO week / this month / this quarter / this year),
each with its expected tasks; the DUE set shrinks as rounds are submitted and
re-opens when a period rolls over.

submit_due_rounds: groups a multi-cadence result set by cadence, creates one
Safety Round per cadence (links its executions, derives overall_result), rolls
all rounds back together on failure, and attempts a manager email afterwards
without letting a mail failure roll back a submitted round.
"""

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, get_first_day, getdate, today

from apex.habitat.api.safety_checklist import (
    get_due_cadences,
    get_tasks_for_cadence,
    submit_due_rounds,
    submit_round,
)
from apex.tests._helpers import _user
from apex.tests.factories import make_building, make_company


class TestSafetyChecklist(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        tag = self._testMethodName

        make_company()
        self.building = make_building(name=f"Checklist Bldg {tag}").name
        self.other_building = make_building(name=f"Checklist Other {tag}").name

        self.task_all = frappe.get_doc(
            {
                "doctype": "Safety Task Catalog",
                "task_code": f"CHK-ALL-{tag}",
                "task_title": f"All-Buildings Task {tag}",
                "department": "Fire Safety",
                "frequency": "Weekly",
                "priority": "High",
                "evidence_required": 0,
                "instructions": "Check all extinguishers.",
                "applicable_to_all_buildings": 1,
                "is_active": 1,
            }
        ).insert(ignore_permissions=True).name

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

        self.cadence_task = {
            "Weekly": self.task_all,
            "Monthly": self.task_other_cadence,
        }
        for cad in ("Daily", "Quarterly", "Annual"):
            self.cadence_task[cad] = frappe.get_doc(
                {
                    "doctype": "Safety Task Catalog",
                    "task_code": f"CHK-{cad[:3].upper()}-{tag}",
                    "task_title": f"{cad} Task {tag}",
                    "department": "Fire Safety",
                    "frequency": cad,
                    "priority": "High",
                    "applicable_to_all_buildings": 1,
                    "is_active": 1,
                }
            ).insert(ignore_permissions=True).name


    def test_get_tasks_returns_exactly_in_scope_tasks(self):
        result = get_tasks_for_cadence(self.building, "Weekly")

        self.assertEqual(result["building"], self.building)
        self.assertEqual(result["cadence"], "Weekly")

        names = {t["name"] for t in result["tasks"]}
        self.assertIn(self.task_all, names, "all-buildings task must be in scope")
        self.assertIn(self.task_scoped, names, "building-scoped task must be in scope")
        self.assertNotIn(
            self.task_other_building, names,
            "a task scoped to another building must be excluded",
        )
        self.assertNotIn(
            self.task_other_cadence, names,
            "a task of another cadence must be excluded",
        )
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
        self.assertEqual(row["department"], "Fire Safety")
        self.assertEqual(row["priority"], "High")
        self.assertEqual(row["evidence_required"], 0)
        self.assertEqual(row["instructions"], "Check all extinguishers.")

    def test_get_tasks_other_cadence_returns_only_that_cadence(self):
        result = get_tasks_for_cadence(self.building, "Monthly")
        names = {t["name"] for t in result["tasks"]}
        self.assertIn(self.task_other_cadence, names)
        self.assertNotIn(self.task_all, names)
        self.assertNotIn(self.task_scoped, names)


    def _lines(self, *statuses):
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

        self.assertEqual(
            frappe.db.get_value("Safety Round", round_name, "docstatus"), 1
        )

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
        with self.assertRaises(frappe.ValidationError):
            submit_round(self.building, "Weekly", today(), self._lines("Good"))

    def test_submit_round_malformed_json_lines_raises_validation_error(self):
        with self.assertRaises(frappe.ValidationError):
            submit_round(self.building, "Weekly", today(), "[not valid json")

    def test_reinspection_round_is_allowed(self):
        submit_round(self.building, "Weekly", today(), self._lines("Good"))
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

    def test_submit_round_throws_without_permission(self):
        original_has_permission = frappe.has_permission
        def mock_has_permission(doctype, ptype="read", doc=None, user=None, throw=False):
            if doctype == "Building" and doc == self.building:
                if throw:
                    frappe.throw("No permission", frappe.PermissionError)
                return False
            return original_has_permission(doctype, ptype, doc, user, throw)

        with patch("apex.habitat.api.safety_checklist.frappe.has_permission", side_effect=mock_has_permission):
            with self.assertRaises(frappe.PermissionError):
                submit_round(self.building, "Weekly", today(), self._lines("Good"))


    def _insert_submitted_round(self, cadence, round_date):
        """Insert + submit a Safety Round (with one execution) on an explicit
        date, bypassing the API so the test can place a round on any day of the
        current period to drive the DUE transitions."""
        rnd = frappe.get_doc(
            {
                "doctype": "Safety Round",
                "building": self.building,
                "round_date": round_date,
                "cadence": cadence,
            }
        ).insert(ignore_permissions=True)
        frappe.get_doc(
            {
                "doctype": "Safety Task Execution",
                "building": self.building,
                "task": self.cadence_task[cadence],
                "execution_date": round_date,
                "execution_status": "Good",
                "safety_round": rnd.name,
            }
        ).insert(ignore_permissions=True).submit()
        rnd.submit()
        return rnd.name

    def _due_cadences(self):
        result = get_due_cadences(self.building)
        self.assertEqual(result["building"], self.building)
        return {block["cadence"] for block in result["due"]}

    def test_due_first_time_all_cadences_due(self):
        result = get_due_cadences(self.building)
        cadences = [block["cadence"] for block in result["due"]]
        self.assertEqual(
            cadences, ["Daily", "Weekly", "Monthly", "Quarterly", "Annual"]
        )
        # `period` is a KIND plus numbers, never a rendered label: the portals hold
        # their own language toggle, so a string built server-side would be frozen in
        # the session's language (safety_checklist.py:158).
        kinds = {
            "Daily": "day",
            "Weekly": "week",
            "Monthly": "month",
            "Quarterly": "quarter",
            "Annual": "year",
        }
        for block in result["due"]:
            self.assertEqual(block["period"]["kind"], kinds[block["cadence"]])
            names = {t["name"] for t in block["tasks"]}
            self.assertIn(self.cadence_task[block["cadence"]], names)

    def test_due_after_daily_round_today_omits_daily(self):
        submit_round(self.building, "Daily", today(), self._lines("Good"))
        due = self._due_cadences()
        self.assertNotIn("Daily", due)
        self.assertEqual(due, {"Weekly", "Monthly", "Quarterly", "Annual"})

    def test_due_weekly_round_this_week_omits_weekly_but_daily_still_due(self):
        iso_monday = add_to_date(
            today(), days=-getdate(today()).weekday(), as_string=True
        )
        self._insert_submitted_round("Weekly", iso_monday)
        due = self._due_cadences()
        self.assertNotIn("Weekly", due, "a Weekly round this ISO week closes Weekly")
        self.assertIn("Daily", due, "Daily is still due — no daily round today")

    def test_due_omits_cadence_with_no_scoped_tasks(self):
        for name in frappe.get_all(
            "Safety Task Catalog", {"frequency": "Daily", "is_active": 1}, pluck="name"
        ):
            frappe.db.set_value("Safety Task Catalog", name, "is_active", 0)
        due = self._due_cadences()
        self.assertNotIn("Daily", due)
        self.assertIn("Weekly", due)

    def test_due_monthly_round_last_month_does_not_close_this_month(self):
        last_month = get_first_day(add_to_date(today(), months=-1), as_str=True)
        self._insert_submitted_round("Monthly", last_month)
        self.assertIn("Monthly", self._due_cadences())


    def _results(self, *pairs):
        """Build a multi-cadence results list from (cadence, status) pairs,
        using each cadence's seeded all-buildings task."""
        return [
            {
                "task": self.cadence_task[cadence],
                "cadence": cadence,
                "execution_status": status,
            }
            for cadence, status in pairs
        ]

    def test_submit_due_rounds_malformed_json_results_raises_validation_error(self):
        with self.assertRaises(frappe.ValidationError):
            submit_due_rounds(self.building, today(), "{not valid json")

    def test_submit_due_rounds_creates_one_round_per_cadence(self):
        results = self._results(
            ("Daily", "Good"), ("Weekly", "Poor"), ("Monthly", "Not Done")
        )
        with patch("apex.habitat.api.safety_checklist.frappe.sendmail"):
            out = submit_due_rounds(self.building, today(), results)

        self.assertTrue(out["ok"])
        self.assertEqual(out["count"], 3)
        self.assertEqual([r["cadence"] for r in out["rounds"]],
                         ["Daily", "Weekly", "Monthly"])
        by_cad = {r["cadence"]: r for r in out["rounds"]}
        self.assertEqual(by_cad["Daily"]["overall_result"], "Pass")
        self.assertEqual(by_cad["Weekly"]["overall_result"], "Needs Attention")
        self.assertEqual(by_cad["Monthly"]["overall_result"], "Fail")

        for cad, r in by_cad.items():
            self.assertEqual(
                frappe.db.get_value("Safety Round", r["safety_round"], "docstatus"), 1
            )
            linked = frappe.get_all(
                "Safety Task Execution",
                filters={"safety_round": r["safety_round"], "docstatus": 1},
                pluck="task",
            )
            self.assertEqual(linked, [self.cadence_task[cad]])

    def test_submit_due_rounds_then_those_cadences_not_due(self):
        results = self._results(("Daily", "Good"), ("Weekly", "Good"))
        with patch("apex.habitat.api.safety_checklist.frappe.sendmail"):
            submit_due_rounds(self.building, today(), results)
        due = self._due_cadences()
        self.assertNotIn("Daily", due)
        self.assertNotIn("Weekly", due)
        self.assertIn("Monthly", due)

    def test_a_failed_cadence_does_not_take_the_successful_ones_with_it(self):
        """Each cadence stands alone (safety_checklist.py:480). One fire door that
        cannot be recorded used to discard the whole daily-plus-weekly walk; the failed
        cadence is now rolled back to its own savepoint and named in ``failed`` while
        the cadences that succeeded stay recorded."""
        self._insert_submitted_round("Weekly", today())
        before_daily = frappe.db.count(
            "Safety Round", {"building": self.building, "cadence": "Daily"}
        )
        results = self._results(("Daily", "Good"), ("Weekly", "Good"))
        with patch("apex.habitat.api.safety_checklist.frappe.sendmail"):
            out = submit_due_rounds(self.building, today(), results)

        self.assertEqual(
            [row["cadence"] for row in out["failed"]],
            ["Weekly"],
            "the duplicate Weekly round must be reported as the cadence that failed",
        )
        self.assertTrue(
            out["failed"][0]["message"],
            "a failed cadence must carry the refusal text, not an empty placeholder",
        )
        self.assertEqual([row["cadence"] for row in out["rounds"]], ["Daily"])
        self.assertTrue(out["ok"], "one recorded cadence is still a successful submit")
        self.assertEqual(
            frappe.db.count("Safety Round", {"building": self.building, "cadence": "Daily"}),
            before_daily + 1,
            "the Daily round must survive the Weekly refusal beside it",
        )


    def _enable_email(self):
        settings = frappe.get_single("Habitat Settings")
        settings.enable_email_notifications = 1
        settings.save(ignore_permissions=True)

    def _disable_email(self):
        settings = frappe.get_single("Habitat Settings")
        settings.enable_email_notifications = 0
        settings.save(ignore_permissions=True)

    def test_submit_due_rounds_emails_manager(self):
        self._enable_email()
        mgr = _user(f"safetymgr_{self._testMethodName}@example.com",
                    "Accommodation Manager")
        results = self._results(("Weekly", "Poor"))
        with patch(
            "apex.habitat.api.safety_checklist.frappe.sendmail"
        ) as mock_send:
            out = submit_due_rounds(self.building, today(), results)

        self.assertTrue(out["emailed"], "manager email must be attempted")
        self.assertEqual(mock_send.call_count, 1)
        self.assertIn(mgr, mock_send.call_args.kwargs["recipients"])
        self.assertIn("Poor", mock_send.call_args.kwargs["message"])

    def test_submit_due_rounds_no_recipient_sets_emailed_false(self):
        self._enable_email()
        for u in frappe.get_all(
            "Has Role", filters={"role": "Accommodation Manager"}, pluck="parent"
        ):
            frappe.db.delete("Has Role", {"parent": u, "role": "Accommodation Manager"})
        results = self._results(("Weekly", "Good"))
        with patch(
            "apex.habitat.api.safety_checklist.frappe.sendmail"
        ) as mock_send:
            out = submit_due_rounds(self.building, today(), results)
        self.assertTrue(out["ok"])
        self.assertFalse(out["emailed"])
        mock_send.assert_not_called()

    def test_submit_due_rounds_mail_failure_does_not_roll_back(self):
        self._enable_email()
        _user(f"safetymgr2_{self._testMethodName}@example.com",
              "Accommodation Manager")
        results = self._results(("Weekly", "Good"))
        with patch(
            "apex.habitat.api.safety_checklist.frappe.sendmail",
            side_effect=Exception("smtp down"),
        ):
            out = submit_due_rounds(self.building, today(), results)
        self.assertTrue(out["ok"])
        self.assertFalse(out["emailed"])
        self.assertEqual(len(out["rounds"]), 1)

    def test_submit_due_rounds_kill_switch_off_sends_no_email(self):
        _user(f"safetymgr3_{self._testMethodName}@example.com", "Accommodation Manager")
        self._disable_email()
        results = self._results(("Weekly", "Good"))
        with patch(
            "apex.habitat.api.safety_checklist.frappe.sendmail"
        ) as mock_send:
            out = submit_due_rounds(self.building, today(), results)
        self.assertTrue(out["ok"])
        self.assertFalse(out["emailed"], "no email may go out while the kill-switch is off")
        mock_send.assert_not_called()
        self.assertEqual(len(out["rounds"]), 1, "the round still records with email off")
        self.assertEqual(
            frappe.db.get_value(
                "Safety Round", out["rounds"][0]["safety_round"], "docstatus"
            ),
            1,
        )
