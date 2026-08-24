# Copyright (c) 2026, afmcoltd


import ast
import inspect
import json
import os
import pathlib

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.apex_core.setup import setup_wizard
from apex.apex_core.setup.salis_support import (
    ISSUE_PRIORITIES,
    ISSUE_TYPES,
    SLA_NAME,
    SLA_PRIORITIES,
    configure_support_sla,
    grant_issue_role_permissions,
)


class TestNoSlaWithoutAnAnswer(FrappeTestCase):

    def test_disabled_never_creates_the_sla(self):
        self.assertIsNone(configure_support_sla(enabled=False))

    def test_an_incomplete_schedule_is_refused_loudly(self):
        for kwargs in (
            {"holiday_list": None, "workdays": ["Monday"], "start_time": "08:00:00", "end_time": "17:00:00"},
            {"holiday_list": "Any", "workdays": [], "start_time": "08:00:00", "end_time": "17:00:00"},
            {"holiday_list": "Any", "workdays": ["Monday"], "start_time": None, "end_time": "17:00:00"},
            {"holiday_list": "Any", "workdays": ["Monday"], "start_time": "08:00:00", "end_time": None},
        ):
            with self.subTest(**kwargs):
                frappe.clear_last_message()
                with self.assertRaises(frappe.ValidationError):
                    configure_support_sla(enabled=True, **kwargs)
                messages = " ".join(
                    str(m) for m in (getattr(frappe.local, "message_log", None) or [])
                )
                self.assertIn(
                    "support start time and support end time are required",
                    messages,
                    "refused for some other reason than the incomplete schedule",
                )

    def test_the_wizard_is_the_only_caller_that_enables_it(self):
        source = inspect.getsource(setup_wizard._apply_salis_support)
        self.assertIn("apex_enable_salis_support_sla", source)
        tree = ast.parse(source)
        disabled_first = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and "configure_support_sla" in ast.unparse(node)
        ]
        self.assertTrue(disabled_first, "the wizard never calls configure_support_sla")


class TestSupportDefaultsAreIdempotent(FrappeTestCase):

    def test_granting_issue_permissions_twice_adds_nothing(self):
        grant_issue_role_permissions()
        before = frappe.db.count("Custom DocPerm", {"parent": "Issue"})
        grant_issue_role_permissions()
        self.assertEqual(frappe.db.count("Custom DocPerm", {"parent": "Issue"}), before)

    def test_the_seeder_runs_at_install_and_at_migrate(self):
        hooks = ast.parse((pathlib.Path(frappe.get_app_path("apex")) / "hooks.py").read_text())
        lists = {
            node.targets[0].id: ast.literal_eval(node.value)
            for node in hooks.body
            if isinstance(node, ast.Assign)
            and getattr(node.targets[0], "id", None) in ("after_install", "after_migrate")
        }
        path = "apex.apex_core.setup.salis_support.grant_issue_role_permissions"
        self.assertIn(path, lists["after_install"])
        self.assertIn(path, lists["after_migrate"])


class TestShippedSupportRecordsAreNamedOnce(FrappeTestCase):

    def test_every_sla_priority_is_a_shipped_issue_priority(self):
        named = {priority for priority, _r, _res, _default in SLA_PRIORITIES}
        self.assertEqual(named - set(ISSUE_PRIORITIES), set())

    def test_exactly_one_sla_priority_is_the_default(self):
        defaults = [p for p, _r, _res, is_default in SLA_PRIORITIES if is_default]
        self.assertEqual(len(defaults), 1)

    def test_the_shipped_names_are_not_empty(self):
        self.assertTrue(ISSUE_TYPES)
        self.assertTrue(ISSUE_PRIORITIES)
        self.assertTrue(SLA_NAME)

    def test_the_fixture_hook_ships_exactly_the_shipped_names(self):
        selected = {
            entry["dt"]: set(entry["filters"][0][2])
            for entry in frappe.get_hooks("fixtures", app_name="apex")
            if isinstance(entry, dict) and entry.get("dt") in ("Issue Type", "Issue Priority")
        }
        self.assertEqual(selected.get("Issue Type"), set(ISSUE_TYPES))
        self.assertEqual(selected.get("Issue Priority"), set(ISSUE_PRIORITIES))

    def test_the_shipped_fixture_files_carry_exactly_the_shipped_names(self):
        fixtures = frappe.get_app_path("apex", "fixtures")
        for filename, expected in (
            ("issue_type.json", ISSUE_TYPES),
            ("issue_priority.json", ISSUE_PRIORITIES),
        ):
            with open(os.path.join(fixtures, filename)) as handle:
                shipped = {row.get("name") for row in json.load(handle)}
            self.assertEqual(shipped, set(expected), filename)
