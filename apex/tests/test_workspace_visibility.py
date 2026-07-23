# Copyright (c) 2026, AFMCO and contributors
"""Regression test: workspace visibility (#24).

File-level test — no Frappe site needed. Uses stdlib only.

Asserts:
- All workspace JSON files are parseable.
- Every workspace has a non-empty "roles" list (no world-visible workspaces).
- Every workspace has a "module" field.
"""

import glob
import json
import os
import unittest

WORKSPACE_GLOB = os.path.join(
    os.path.dirname(__file__),
    "..",
    "habitat",
    "workspace",
    "*",
    "*.json",
)

# [#q3fp4l]
_APP = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
ALL_WORKSPACE_GLOB = os.path.join(_APP, "*", "workspace", "*", "*.json")
ALL_CHART_GLOB = os.path.join(_APP, "*", "dashboard_chart", "*", "*.json")


def _workspace_files():
    return sorted(glob.glob(WORKSPACE_GLOB))


def _all_workspace_files():
    return sorted(glob.glob(ALL_WORKSPACE_GLOB))


def _chart_record_names():
    """Every on-disk is_standard Dashboard Chart record name."""
    names = set()
    for path in glob.glob(ALL_CHART_GLOB):
        with open(path, encoding="utf-8") as fh:
            names.add(json.load(fh).get("name") or os.path.basename(os.path.dirname(path)))
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


class TestWorkspaceVisibility(unittest.TestCase):

    def test_workspace_files_exist(self):
        """At least one workspace JSON file must be present."""
        files = _workspace_files()
        self.assertGreater(
            len(files),
            0,
            "No workspace JSON files found under apex/habitat/workspace/*/",
        )

    def test_all_workspaces_parseable(self):
        """Every workspace JSON file must be valid JSON."""
        for path in _workspace_files():
            with self.subTest(path=os.path.basename(os.path.dirname(path))):
                with open(path, encoding="utf-8") as fh:
                    try:
                        json.load(fh)
                    except json.JSONDecodeError as exc:
                        self.fail(f"{path} is not valid JSON: {exc}")

    def test_all_workspaces_have_module_field(self):
        """Every workspace JSON must have a 'module' field."""
        for path in _workspace_files():
            workspace_name = os.path.basename(os.path.dirname(path))
            with self.subTest(workspace=workspace_name):
                with open(path, encoding="utf-8") as fh:
                    data = json.load(fh)
                self.assertIn(
                    "module",
                    data,
                    f"Workspace '{workspace_name}' is missing the 'module' field.",
                )
                self.assertTrue(
                    data["module"],
                    f"Workspace '{workspace_name}' has an empty 'module' field.",
                )

    def test_all_workspaces_have_nonempty_roles(self):
        """Every workspace must have a non-empty 'roles' list.

        A workspace with an empty roles list is world-visible (accessible to
        all authenticated users regardless of role), which violates the
        principle of least privilege used in this application.
        """
        for path in _workspace_files():
            workspace_name = os.path.basename(os.path.dirname(path))
            with self.subTest(workspace=workspace_name):
                with open(path, encoding="utf-8") as fh:
                    data = json.load(fh)
                roles = data.get("roles", [])
                self.assertIsInstance(
                    roles,
                    list,
                    f"Workspace '{workspace_name}': 'roles' must be a list, got {type(roles).__name__}.",
                )
                self.assertGreater(
                    len(roles),
                    0,
                    f"Workspace '{workspace_name}' has an empty 'roles' list — it is world-visible. "
                    "Add at least one role restriction.",
                )


class TestWorkspaceHeadlineCharts(unittest.TestCase):
    """Each domain workspace pins a single headline Dashboard Chart (P-094).

    The earlier lean design shipped no charts; P-092/P-094 superseded it — every
    domain workspace now surfaces one headline chart. The load-bearing invariant
    is the silent-drop trap: a workspace that references a chart record absent
    from disk renders nothing with no error. This guard enforces that every wired
    chart resolves to an on-disk is_standard Dashboard Chart record.
    """

    def test_every_wired_chart_exists_on_disk(self):
        # [#6q5sa3]
        missing = _workspace_referenced_charts() - _chart_record_names()
        self.assertEqual(
            missing,
            set(),
            f"workspace chart references with no matching on-disk record: {sorted(missing)}",
        )

    def test_scan_is_non_vacuous(self):
        # [#1w1s6p]
        self.assertTrue(_chart_record_names(), "no Dashboard Chart records discovered on disk")
        self.assertTrue(_all_workspace_files(), "no workspace JSON discovered across modules")
        self.assertTrue(
            _workspace_referenced_charts(),
            "no workspace headline charts discovered — the P-094 headline-chart design expects them",
        )


class TestWorkspaceOperationalLinkSeparation(unittest.TestCase):
    """Background and portal-owned records stay out of daily workspaces."""

    # A-042 retired the per-role landing workspaces; the daily-hygiene guard now
    # covers only the business-domain workspaces that absorbed their content.
    REMOVED_LINKS = {
        "salis/workspace/fleet/fleet.json": {"Driver Attendance", "Fuel Daily Log"},
        "habitat/workspace/safety/safety.json": {"Scheduled Task Instance"},
        "salis/workspace/masar/masar.json": {"Trip Start Log", "Trip Boarding Event"},
    }

    def test_daily_workspaces_exclude_portal_and_engine_records(self):
        for path, forbidden_targets in self.REMOVED_LINKS.items():
            with self.subTest(workspace=path):
                link_targets = {row.get("link_to") for row in _workspace_link_records(path)}
                self.assertTrue(
                    forbidden_targets.isdisjoint(link_targets),
                    f"{path} still exposes non-daily links: {sorted(forbidden_targets & link_targets)}",
                )

    def test_driver_attendance_summary_report_remains_available(self):
        for path in ("salis/workspace/fleet/fleet.json",):
            with self.subTest(workspace=path):
                links = _workspace_link_records(path)
                self.assertIn(
                    ("Driver Attendance Summary", "Report"),
                    {(row.get("link_to"), row.get("link_type")) for row in links},
                )


if __name__ == "__main__":
    unittest.main()
