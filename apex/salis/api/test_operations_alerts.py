# Copyright (c) 2026, afmcoltd
"""Coverage for the operations-queue action API (``apex.salis.api.operations_alerts``).

Exercises every callable in the module: the read-only ``get_open_alerts`` (project
scope, severity threshold, aging defaults, the resolved-since delta) and the write
actions (acknowledge, assign, unassign, snooze, resolve, and their bulk variants),
which resolve a queue row back to its ASSIGNED document and enforce ``write`` on
THAT document through the same project-scoped permission hook the dispatch board
uses. Fixtures are two fresh vehicles in two disjoint projects and a Fleet
Supervisor granted only one of them, so a scope assertion is proved against a real
User Permission rather than an Administrator session.
"""

from __future__ import annotations

import frappe
from frappe.desk.form import assign_to
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, now_datetime

from apex.salis.api import operations_alerts
from apex.tests._helpers import _grant_project, _user, as_user
from apex.tests.factories import fixture_tag, make_project, make_vehicle


class TestOperationsAlerts(FrappeTestCase):
    """Fixtures: two projects, a vehicle in each, a Fleet Supervisor scoped to
    only the first, and an unscoped Fleet Manager."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        tag = fixture_tag()
        cls.proj_a = make_project(f"OpsAlerts A {tag}")
        cls.proj_b = make_project(f"OpsAlerts B {tag}")
        cls.veh_a = make_vehicle(f"OA-A-{tag}", project=cls.proj_a)
        cls.veh_b = make_vehicle(f"OA-B-{tag}", project=cls.proj_b)
        cls.sup_a = _user(f"opsalerts_sup_a_{tag}@example.com", "Fleet Supervisor")
        _grant_project(cls.sup_a, cls.proj_a)
        cls.empty_sup = _user(f"opsalerts_sup_empty_{tag}@example.com", "Fleet Supervisor")
        cls.mgr = _user(f"opsalerts_mgr_{tag}@example.com", "Fleet Manager")

    def setUp(self):
        frappe.set_user("Administrator")
        self._created_todos: list[str] = []

    def tearDown(self):
        frappe.set_user("Administrator")
        for name in self._created_todos:
            if frappe.db.exists("ToDo", name):
                frappe.delete_doc("ToDo", name, ignore_permissions=True, force=True)

    def _queue_todo(self, reference_name, priority="High", allocated_to="Administrator", status="Open"):
        """Insert an open Fleet Supervisor queue row on a Salis Vehicle and track
        it for teardown; returns the ToDo document."""
        todo = frappe.get_doc(
            {
                "doctype": "ToDo",
                "reference_type": "Salis Vehicle",
                "reference_name": reference_name,
                "status": status,
                "priority": priority,
                "description": "operations_alerts coverage fixture",
                "allocated_to": allocated_to,
            }
        ).insert(ignore_permissions=True)
        self._created_todos.append(todo.name)
        return todo

    def test_scoped_user_with_no_permitted_project_sees_no_alerts(self):
        """No alert fires for a scoped caller granted no project at all."""
        self._queue_todo(self.veh_a)
        with as_user(self.empty_sup):
            result = operations_alerts.get_open_alerts()
        self.assertEqual(result["alerts"], [])
        self.assertEqual(result["summary"]["total"], 0)

    def test_scoped_user_sees_only_alerts_within_permitted_project(self):
        """A scoped supervisor's alert list stops at their own project's vehicle."""
        self._queue_todo(self.veh_a)
        self._queue_todo(self.veh_b)
        with as_user(self.sup_a):
            result = operations_alerts.get_open_alerts()
        vehicles_seen = {a["vehicle"] for a in result["alerts"]}
        self.assertIn(self.veh_a, vehicles_seen)
        self.assertNotIn(self.veh_b, vehicles_seen)

    def test_unscoped_user_sees_alerts_across_projects(self):
        """An oversight role (unscoped) sees rows from both projects."""
        self._queue_todo(self.veh_a)
        self._queue_todo(self.veh_b)
        with as_user(self.mgr):
            result = operations_alerts.get_open_alerts()
        vehicles_seen = {a["vehicle"] for a in result["alerts"]}
        self.assertIn(self.veh_a, vehicles_seen)
        self.assertIn(self.veh_b, vehicles_seen)

    def test_alert_severity_reflects_todo_priority_threshold(self):
        """Severity is derived from the ToDo priority: High/Low sit on opposite
        sides of the Critical/Info threshold, never blended."""
        self._queue_todo(self.veh_a, priority="High")
        self._queue_todo(self.veh_b, priority="Low")
        with as_user(self.mgr):
            result = operations_alerts.get_open_alerts()
        by_vehicle = {a["vehicle"]: a["severity"] for a in result["alerts"]}
        self.assertEqual(by_vehicle[self.veh_a], "Critical")
        self.assertEqual(by_vehicle[self.veh_b], "Info")

    def test_severity_param_narrows_to_one_threshold(self):
        """Passing ``severity`` excludes every row that did not cross that
        threshold, even when both are in scope."""
        self._queue_todo(self.veh_a, priority="High")
        self._queue_todo(self.veh_b, priority="Low")
        with as_user(self.mgr):
            result = operations_alerts.get_open_alerts(severity="Critical")
        vehicles_seen = {a["vehicle"] for a in result["alerts"]}
        self.assertIn(self.veh_a, vehicles_seen)
        self.assertNotIn(self.veh_b, vehicles_seen)
        self.assertTrue(all(a["severity"] == "Critical" for a in result["alerts"]))

    def test_aging_thresholds_falls_back_to_defaults(self):
        """With every Salis Settings aging field blank, ``_aging_thresholds``
        reports the module's own hard-coded defaults."""
        originals = {
            field: frappe.db.get_single_value("Salis Settings", field)
            for field in operations_alerts.AGING_SETTING.values()
        }
        for field in operations_alerts.AGING_SETTING.values():
            frappe.db.set_single_value("Salis Settings", field, 0)
        self.addCleanup(
            lambda: [
                frappe.db.set_single_value("Salis Settings", field, originals[field])
                for field in operations_alerts.AGING_SETTING.values()
            ]
        )
        self.assertEqual(operations_alerts._aging_thresholds(), operations_alerts.AGING_DEFAULT)

    def test_aging_thresholds_reads_settings_override(self):
        """A Salis Settings value overrides the hard-coded default for that
        severity only."""
        field = operations_alerts.AGING_SETTING["Critical"]
        original = frappe.db.get_single_value("Salis Settings", field)
        frappe.db.set_single_value("Salis Settings", field, 2)
        self.addCleanup(lambda: frappe.db.set_single_value("Salis Settings", field, original))
        self.assertEqual(operations_alerts._aging_thresholds()["Critical"], 2)

    def test_resolved_since_counts_closed_todos_for_unscoped(self):
        """``_resolved_since`` counts a queue row drained after the cutoff, for an
        unscoped caller (``plates is None``)."""
        since = add_to_date(now_datetime(), hours=-1)
        todo = self._queue_todo(self.veh_a)
        frappe.db.set_value("ToDo", todo.name, "status", "Closed")
        count = operations_alerts._resolved_since(str(since), None)
        self.assertGreaterEqual(count, 1)

    def test_resolved_since_returns_zero_when_scoped_or_unset(self):
        """A scoped caller (a plates list) or a missing ``since`` both read as
        zero rather than leak another project's activity."""
        self.assertEqual(operations_alerts._resolved_since(str(now_datetime()), [self.veh_a]), 0)
        self.assertEqual(operations_alerts._resolved_since(None, None), 0)

    def test_queue_ref_checked_raises_when_row_not_found(self):
        """A name that is not an open queue ToDo throws rather than resolving to
        nothing."""
        with self.assertRaises(frappe.ValidationError):
            operations_alerts._queue_ref_checked(f"NO-SUCH-QUEUE-ROW-{fixture_tag()}")

    def test_queue_ref_checked_denies_write_outside_project_scope(self):
        """A scoped supervisor cannot resolve a queue row anchored to a vehicle
        outside their permitted project — the write check is real, not a
        board-role side door."""
        todo = self._queue_todo(self.veh_b)
        with as_user(self.sup_a):
            with self.assertRaises(frappe.PermissionError):
                operations_alerts._queue_ref_checked(todo.name)

    def test_acknowledge_alert_reports_no_transition(self):
        """Acknowledging a row permission-checks and reports no state change."""
        todo = self._queue_todo(self.veh_a)
        with as_user(self.sup_a):
            result = operations_alerts.acknowledge_alert(todo.name)
        self.assertEqual(result["status"], "Open")
        self.assertFalse(result["acknowledged"])

    def test_bulk_acknowledge_alerts_reports_the_row_it_acknowledged(self):
        """A row the caller may act on should come back in ``acknowledged`` —
        exactly what bulk_assign_alerts and bulk_snooze_alerts already report for
        a permitted row."""
        # Regression guard for A-564: bulk_acknowledge_alerts once read the always-False
        # "acknowledged" key, so the desk's "{0} acknowledged" banner always said nought.
        # checks acknowledge_alert(name).get("acknowledged"), but acknowledge_alert
        # (operations_alerts.py:197) always returns acknowledged=False — so this
        # bulk action can never report a row as acknowledged, even on success.
        # Every sibling bulk action checks "ok" instead; this is the one outlier.
        todo = self._queue_todo(self.veh_a)
        with as_user(self.sup_a):
            result = operations_alerts.bulk_acknowledge_alerts([todo.name])
        self.assertIn(todo.name, result["acknowledged"])

    def test_assign_alert_adds_caller_as_assignee(self):
        """Assigning with no explicit ``user`` takes ownership as the caller, and
        the row lists the caller among its assignees."""
        todo = self._queue_todo(self.veh_a)
        with as_user(self.sup_a):
            result = operations_alerts.assign_alert(todo.name)
        self.assertIn(self.sup_a, result["assignees"])

    def test_unassign_alert_removes_assignee(self):
        """Dropping the caller from a queue row's document actually closes the
        underlying ToDo, not merely the reported list."""
        frappe.set_user("Administrator")
        assign_to.add({"assign_to": [self.sup_a], "doctype": "Salis Vehicle", "name": self.veh_a})
        assignment_name = frappe.db.get_value(
            "ToDo",
            {
                "reference_type": "Salis Vehicle",
                "reference_name": self.veh_a,
                "allocated_to": self.sup_a,
                "status": "Open",
            },
            "name",
        )
        self._created_todos.append(assignment_name)
        with as_user(self.sup_a):
            result = operations_alerts.unassign_alert(assignment_name)
        self.assertNotIn(self.sup_a, result["assignees"])
        self.assertEqual(frappe.db.get_value("ToDo", assignment_name, "status"), "Cancelled")

    def test_bulk_assign_alerts_skips_row_outside_scope(self):
        """A row the caller may not act on is skipped, not trusted from the
        client's own name list."""
        todo_a = self._queue_todo(self.veh_a)
        todo_b = self._queue_todo(self.veh_b)
        with as_user(self.sup_a):
            result = operations_alerts.bulk_assign_alerts([todo_a.name, todo_b.name])
        self.assertIn(todo_a.name, result["assigned"])
        self.assertNotIn(todo_b.name, result["assigned"])

    def test_snooze_alert_and_target_resolve_presets(self):
        """A queue row carries no snooze state (reports null); the underlying
        resolver still turns a named preset or an explicit datetime into a real
        deadline, and returns None for neither."""
        todo = self._queue_todo(self.veh_a)
        with as_user(self.sup_a):
            result = operations_alerts.snooze_alert(todo.name, preset="tomorrow")
        self.assertIsNone(result["snooze_until"])
        self.assertIsNone(operations_alerts._snooze_target())
        self.assertIsNotNone(operations_alerts._snooze_target(preset="2d"))
        self.assertEqual(
            str(operations_alerts._snooze_target(until="2026-09-01 10:00:00")),
            "2026-09-01 10:00:00",
        )

    def test_bulk_snooze_alerts_skips_row_outside_scope(self):
        """The multi-select snooze re-checks write per row exactly like bulk
        assign, so an out-of-scope row is dropped from the result."""
        todo_a = self._queue_todo(self.veh_a)
        todo_b = self._queue_todo(self.veh_b)
        with as_user(self.sup_a):
            result = operations_alerts.bulk_snooze_alerts([todo_a.name, todo_b.name], preset="2d")
        self.assertIn(todo_a.name, result["snoozed"])
        self.assertNotIn(todo_b.name, result["snoozed"])

    def test_resolve_alert_closes_open_assignment(self):
        """Resolving closes every open assignment on the referenced document and
        reports the transition."""
        frappe.set_user("Administrator")
        assign_to.add({"assign_to": [self.sup_a], "doctype": "Salis Vehicle", "name": self.veh_a})
        assignment_name = frappe.db.get_value(
            "ToDo",
            {
                "reference_type": "Salis Vehicle",
                "reference_name": self.veh_a,
                "allocated_to": self.sup_a,
                "status": "Open",
            },
            "name",
        )
        self._created_todos.append(assignment_name)
        with as_user(self.sup_a):
            result = operations_alerts.resolve_alert(assignment_name, note="handled")
        self.assertTrue(result["resolved"])
        self.assertEqual(result["status"], "Resolved")
        remaining = frappe.get_all(
            "ToDo",
            filters={
                "reference_type": "Salis Vehicle",
                "reference_name": self.veh_a,
                "status": ["in", ["Open", "Overdue"]],
            },
        )
        self.assertEqual(remaining, [])
