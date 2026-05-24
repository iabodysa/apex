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


def _workspace_files():
    return sorted(glob.glob(WORKSPACE_GLOB))


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


if __name__ == "__main__":
    unittest.main()
