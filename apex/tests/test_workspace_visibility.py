# Copyright (c) 2026, AFMCO and contributors
"""Regression test: workspace visibility (#24).

WORLD-VISIBILITY IS ASKED OF THE FRAMEWORK, NOT OF THE JSON. An empty ``roles``
child table is not a cosmetic omission: ``frappe.desk.desktop.Workspace.is_permitted``
(frappe/desk/desktop.py:78-93) returns True unconditionally the moment
``self.doc.roles`` is empty — that IS the mechanism that makes a workspace visible to
every authenticated user regardless of role. A guard that only checked the shipped
JSON could go stale the moment a patch or a hand fix touched the row on a live site
without touching the file; this asks the same question ``is_permitted`` asks, against
the actual site.

SCOPE UNCHANGED FROM THE ORIGINAL: Habitat-module workspaces only (the previous
``WORKSPACE_GLOB`` matched only ``apex/habitat/workspace/*/*.json``), preserved here
as-is rather than widened, because widening it is a policy decision, not a test-format
one. Widening the scope to every Apex-owned workspace does turn up one workspace
outside Habitat with an empty ``roles`` table — the top-level ``Apex`` hub, which
carries no data of its own and only links onward to module roots that each enforce
their own role. That may be a deliberate navigational-index design (frappe's own
stock ``Home`` workspace ships the same way) or an oversight; it is flagged for the
owner rather than decided here.

The chart/link guards below stay file-level: what they defend (a dangling chart
reference, a retired link resurfacing on a daily workspace) is a property of the
shipped is_standard record set as a whole, which the site does not expose any single
query for.
"""

import glob
import json
import os
import unittest

import apex
import frappe
from frappe.tests.utils import FrappeTestCase

# Rooted at the INSTALLED package. Walking up from this file lands in .claude/tests/, so
# both globs matched nothing and "every workspace has roles" was asserted over an empty
# list — a guard that cannot fail.
_APP = os.path.dirname(os.path.abspath(apex.__file__))

ALL_WORKSPACE_GLOB = os.path.join(_APP, "*", "workspace", "*", "*.json")
ALL_CHART_GLOB = os.path.join(_APP, "*", "dashboard_chart", "*", "*.json")


def _all_workspace_files():
    return sorted(glob.glob(ALL_WORKSPACE_GLOB))


def _chart_record_names():
    """Every on-disk is_standard Dashboard Chart record name."""
    names = set()
    for path in glob.glob(ALL_CHART_GLOB):
        with open(path, encoding="utf-8") as fh:
            names.add(json.load(fh).get("name") or os.path.basename(os.path.dirname(path)))
    return names


def _charts_in(path):
    """The chart names this one workspace file pins, by either mechanism."""
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    names = {c["chart_name"] for c in data.get("charts", []) if c.get("chart_name")}
    try:
        blocks = json.loads(data.get("content") or "[]")
    except (ValueError, TypeError):
        return names
    for block in blocks:
        if isinstance(block, dict) and block.get("type") == "chart":
            name = (block.get("data") or {}).get("chart_name")
            if name:
                names.add(name)
    return names


def _workspace_referenced_charts():
    """Every chart pinned onto a workspace, via the charts[] array or a content block."""
    referenced = set()
    for path in _all_workspace_files():
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        for chart in data.get("charts", []):
            if chart.get("chart_name"):
                referenced.add(chart["chart_name"])
        try:
            blocks = json.loads(data.get("content") or "[]")
        except (ValueError, TypeError):
            continue
        for block in blocks:
            if isinstance(block, dict) and block.get("type") == "chart":
                name = (block.get("data") or {}).get("chart_name")
                if name:
                    referenced.add(name)
    return referenced


def _workspace_link_records(relative_path):
    """Return the native Link rows from one workspace JSON record."""
    path = os.path.join(_APP, *relative_path.split("/"))
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    return [row for row in data.get("links", []) if row.get("type") == "Link"]


def _habitat_workspace_names():
    """Every Workspace name in the Habitat module — the same scope the retired
    JSON glob (``apex/habitat/workspace/*/*.json``) covered."""
    return frappe.get_all("Workspace", filters={"module": "Habitat"}, pluck="name")


class TestWorkspaceVisibility(FrappeTestCase):
    """No shipped workspace may be visible to every authenticated user regardless of role.

    The previous version opened each workspace's JSON and asserted the ``roles`` array
    it found there was non-empty — a Change Detector Test pinning the file's text. What
    an operator actually meets is decided by ``Workspace.is_permitted`` reading the
    ``roles`` child table on the SITE, so this asks that question directly and proves,
    on a throwaway workspace, that the mechanism it relies on behaves the way the guard
    assumes.
    """

    def test_no_shipped_workspace_has_an_empty_roles_table(self):
        names = _habitat_workspace_names()
        self.assertGreater(len(names), 0, "no Habitat workspace found — scope drifted")
        world_visible = [
            name
            for name in names
            if not frappe.db.count(
                "Has Role", {"parent": name, "parenttype": "Workspace", "parentfield": "roles"}
            )
        ]
        self.assertEqual(
            world_visible,
            [],
            "these shipped workspaces carry no role restriction, so "
            "frappe.desk.desktop.Workspace.is_permitted() admits every authenticated "
            f"user regardless of role: {world_visible}",
        )

    def test_an_empty_roles_table_is_what_makes_is_permitted_admit_everyone(self):
        """Guard-of-the-guard: proves the mechanism the assertion above relies on.

        A DocPerm-style read/write check is irrelevant here — Workspace visibility in
        the sidebar is decided by ``is_permitted()`` alone, which reads only the
        ``roles`` child table (frappe/desk/desktop.py:78-93). This drives that function
        directly on two throwaway documents rather than trusting a description of it.
        """
        from frappe.desk.desktop import Workspace as DesktopWorkspace

        frappe.set_user("Administrator")
        stranger = "workspace_visibility_stranger@example.com"
        if not frappe.db.exists("User", stranger):
            frappe.get_doc(
                {"doctype": "User", "email": stranger, "first_name": "Stranger", "send_welcome_email": 0}
            ).insert(ignore_permissions=True)

        open_ws = frappe.get_doc(
            {"doctype": "Workspace", "label": "_Test Open WS", "title": "_Test Open WS", "public": 1}
        ).insert(ignore_permissions=True)
        self.addCleanup(open_ws.delete, ignore_permissions=True)

        guarded_ws = frappe.get_doc(
            {
                "doctype": "Workspace",
                "label": "_Test Guarded WS",
                "title": "_Test Guarded WS",
                "public": 1,
                "roles": [{"role": "System Manager"}],
            }
        ).insert(ignore_permissions=True)
        self.addCleanup(guarded_ws.delete, ignore_permissions=True)

        frappe.set_user(stranger)
        try:
            self.assertTrue(
                DesktopWorkspace(open_ws.as_dict(), minimal=True).is_permitted(),
                "a workspace with an empty roles table must admit any authenticated user",
            )
            self.assertFalse(
                DesktopWorkspace(guarded_ws.as_dict(), minimal=True).is_permitted(),
                "a workspace restricted to System Manager must refuse a user without it",
            )
        finally:
            frappe.set_user("Administrator")


class TestWorkspaceHeadlineCharts(unittest.TestCase):
    """Each domain workspace pins a single headline Dashboard Chart.

    The earlier lean design shipped no charts; every domain workspace now surfaces
    one headline chart. The load-bearing invariant
    is the silent-drop trap: a workspace that references a chart record absent
    from disk renders nothing with no error. This guard enforces that every wired
    chart resolves to an on-disk is_standard Dashboard Chart record.
    """

    def test_every_wired_chart_exists_on_disk(self):
        missing = _workspace_referenced_charts() - _chart_record_names()
        self.assertEqual(
            missing,
            set(),
            f"workspace chart references with no matching on-disk record: {sorted(missing)}",
        )

    def test_scan_is_non_vacuous(self):
        self.assertTrue(_chart_record_names(), "no Dashboard Chart records discovered on disk")
        self.assertTrue(_all_workspace_files(), "no workspace JSON discovered across modules")

    def test_no_operator_workspace_carries_a_chart(self):
        """Owner rule: a workspace carries links, cards, shortcuts and lists — never a chart.

        This replaces the guard that asserted the opposite. That one required every persona
        root to open on a headline chart, which was the design until the rule was set; a
        guard encoding a retired policy fails honest work and has to be re-aimed, not
        silenced. The sibling that grades a chart reference against the shipped Dashboard
        Chart records is the load-bearing half and still runs.

        ONE WORKSPACE IS EXEMPT BY OWNER DECISION, and it is named rather than
        pattern-matched so that adding a second requires editing this line. ``Back Engines``
        is not a screen an operator opens: it is System Manager only, sits under Apex Core,
        and its own content block says it exists "so that nothing is invisible" — it is the
        inventory of every chart and card that is built but not placed. The rule protects
        daily screens from becoming dashboards; an inventory of the unplaced is the opposite
        of that, and stripping its 46 rows would hide exactly what it was built to show.
        The exemption was proposed on that reasoning and ratified by the owner, so it is not
        a reader's judgement to re-open.

        The assertion is therefore stronger than a bare emptiness check: it pins WHICH file
        may carry charts, so a chart landing on any other workspace still fails, and a
        second exempt workspace cannot appear without a reader deciding to allow it.
        """
        exempt = "apex/apex_core/workspace/back_engines/back_engines.json"
        repo = os.path.dirname(_APP)
        carriers = sorted(
            os.path.relpath(path, repo) for path in _all_workspace_files() if _charts_in(path)
        )
        self.assertEqual(
            carriers,
            [exempt],
            "charts belong in a dashboard or a report, not on a workspace — only "
            f"{exempt} is exempt, and it is the inventory of unplaced charts",
        )


class TestWorkspaceOperationalLinkSeparation(unittest.TestCase):
    """Background and portal-owned records stay out of daily workspaces."""

    # The per-role landing workspaces are retired; the daily-hygiene guard now
    # covers only the business-domain workspaces that absorbed their content.
    REMOVED_LINKS = {
        "salis/workspace/fleet/fleet.json": {"Driver Attendance", "Fuel Daily Log"},
        # The Safety workspace was folded into Housing and Safety; keyed on the retired
        # path this subtest raised FileNotFoundError instead of grading anything.
        "habitat/workspace/housing_and_safety/housing_and_safety.json": {
            "Scheduled Task Instance"
        },
        # The Masar child workspace folded into the Salis root, which now carries
        # its transport navigation — so the same engine records stay out of Salis.
        "salis/workspace/salis/salis.json": {"Trip Start Log", "Trip Boarding Event"},
    }

    def test_daily_workspaces_exclude_portal_and_engine_records(self):
        for path, forbidden_targets in self.REMOVED_LINKS.items():
            with self.subTest(workspace=path):
                link_targets = {row.get("link_to") for row in _workspace_link_records(path)}
                self.assertTrue(
                    forbidden_targets.isdisjoint(link_targets),
                    f"{path} still exposes non-daily links: {sorted(forbidden_targets & link_targets)}",
                )

    def test_driver_attendance_summary_report_has_exactly_one_home(self):
        """Owner rule: no report and no DocType appears on two workspaces.

        This guard asserts the report has exactly ONE home. Reachability is what it
        defends, and one home satisfies that; two is the thing the rule forbids.
        Asserting the COUNT keeps the protection — a report that falls off every
        workspace still fails here.
        """
        homes = [
            path
            for path in _all_workspace_files()
            for row in _workspace_link_records(os.path.relpath(path, _APP))
            if (row.get("link_to"), row.get("link_type")) == ("Driver Attendance Summary", "Report")
        ]
        self.assertEqual(
            len(homes),
            1,
            "Driver Attendance Summary must sit on exactly one workspace; found "
            f"{len(homes)}: {[os.path.relpath(p, _APP) for p in homes]}",
        )


if __name__ == "__main__":
    unittest.main()
