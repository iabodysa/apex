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

# All modules' workspaces / chart records, for the cross-module no-chart invariant.
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


class TestWorkspaceVisibility(unittest.TestCase):

    def test_workspace_files_exist(self):
        """At least one workspace JSON file must be present."""
        files = _workspace_files()
        self.assertGreater(
            len(files),
            0,
            "No workspace JSON files found under apex_habitat/habitat/workspace/*/",
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


class TestNoChartWorkspaceDesign(unittest.TestCase):
    """The lean public-workspace design ships NO charts on any workspace.

    Every on-disk is_standard Dashboard Chart record is therefore an intentional
    orphan (reachable only from the Dashboard Chart list, never pinned to a
    workspace). This guard keeps that invariant from silently regressing: it fails
    the moment a chart is wired onto a workspace, or a workspace references a chart
    record that does not exist on disk.
    """

    def test_no_chart_is_wired_to_any_workspace(self):
        wired = _workspace_referenced_charts()
        self.assertEqual(
            wired,
            set(),
            "the no-chart workspace design forbids pinning a Dashboard Chart to a "
            f"workspace; remove these chart references: {sorted(wired)}",
        )

    def test_workspace_chart_refs_exist_on_disk(self):
        # A workspace must never point at a chart record absent from disk; with the
        # wired set empty this is vacuously true, but it guards the day a chart is
        # (re-)wired against a deleted record.
        missing = _workspace_referenced_charts() - _chart_record_names()
        self.assertEqual(
            missing,
            set(),
            f"workspace chart references with no matching on-disk record: {sorted(missing)}",
        )

    def test_scan_is_non_vacuous(self):
        # Guard the guard: a glob that silently finds nothing would pass the
        # invariant above for free. Chart records exist on disk and the workspace
        # scan reaches every module's workspaces.
        self.assertTrue(_chart_record_names(), "no Dashboard Chart records discovered on disk")
        self.assertTrue(_all_workspace_files(), "no workspace JSON discovered across modules")


if __name__ == "__main__":
    unittest.main()
