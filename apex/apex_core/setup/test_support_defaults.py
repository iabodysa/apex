# Copyright (c) 2026, afmcoltd

"""No site gets a support contract it was never asked about.

An SLA that appears on its own promises a response time nobody agreed to, and it is
worse than none: a ticket then looks answered-on-time or late against hours the operator
never chose. So the rule is that a site-specific schedule — the SLA, the Holiday List and
the support hours — is CHOSEN in setup, while the site-independent defaults are seeded
idempotently.

These assert the choosing, the refusal and the idempotency. The Issue Type and Issue
Priority refusals are covered where they live.
"""

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
    """The defect this guards: an after_migrate seed creating a 24x7 SLA silently."""

    def test_disabled_never_creates_the_sla(self):
        self.assertIsNone(configure_support_sla(enabled=False))

    def test_an_incomplete_schedule_is_refused_loudly(self):
        """Half a schedule is the dangerous case: workdays with no hours accepts every
        ticket and promises nothing, which reads on screen as configured.

        The refusal is matched on ITS OWN MESSAGE, not on the exception class. Every
        later step of this function also raises ValidationError — a missing Holiday
        List row, a bad time — so asserting the class alone passes even when the
        completeness check is deleted. Measured: with the check removed the
        class-only assertion still went green.
        """
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
        """Read from the source: an enable that reaches a seeder instead of the wizard
        is exactly the silent creation this card retired."""
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
    """They run at install AND at migrate, so a second run must change nothing."""

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
    """The refusals and the SLA read their names from one place, so they cannot drift."""

    def test_every_sla_priority_is_a_shipped_issue_priority(self):
        """An SLA naming a priority the app does not ship would reference a row that
        disappears the moment nobody recreates it."""
        named = {priority for priority, _r, _res, _default in SLA_PRIORITIES}
        self.assertEqual(named - set(ISSUE_PRIORITIES), set())

    def test_exactly_one_sla_priority_is_the_default(self):
        defaults = [p for p, _r, _res, is_default in SLA_PRIORITIES if is_default]
        self.assertEqual(len(defaults), 1)

    def test_the_shipped_names_are_not_empty(self):
        """The positive control: a refusal over an empty tuple refuses nothing."""
        self.assertTrue(ISSUE_TYPES)
        self.assertTrue(ISSUE_PRIORITIES)
        self.assertTrue(SLA_NAME)

    def test_the_fixture_hook_ships_exactly_the_shipped_names(self):
        """The third consumer, and the one that used to hold its own copy: a name the
        fixtures hook does not select is never installed, so the refusal guards a row
        that is not there and the SLA hangs off a priority that does not exist."""
        selected = {
            entry["dt"]: set(entry["filters"][0][2])
            for entry in frappe.get_hooks("fixtures", app_name="apex")
            if isinstance(entry, dict) and entry.get("dt") in ("Issue Type", "Issue Priority")
        }
        self.assertEqual(selected.get("Issue Type"), set(ISSUE_TYPES))
        self.assertEqual(selected.get("Issue Priority"), set(ISSUE_PRIORITIES))

    def test_the_shipped_fixture_files_carry_exactly_the_shipped_names(self):
        """The fixture FILE is what installs; the tuple only selects. A name in the
        tuple with no row in the file selects nothing and installs nothing, and the
        refusal then guards a record the site never received."""
        fixtures = frappe.get_app_path("apex", "fixtures")
        for filename, expected in (
            ("issue_type.json", ISSUE_TYPES),
            ("issue_priority.json", ISSUE_PRIORITIES),
        ):
            with open(os.path.join(fixtures, filename)) as handle:
                shipped = {row.get("name") for row in json.load(handle)}
            self.assertEqual(shipped, set(expected), filename)
