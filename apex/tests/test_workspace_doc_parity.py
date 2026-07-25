# Copyright (c) 2026, AFMCO and contributors
"""Section 1 of docs/WORKSPACE-DESIGN.md must match the shipped Workspace JSON.

That published table states, per workspace, the module that owns it, where it
sits in the sidebar, and the exact list of roles it grants. Nothing under
`apex/` or `scripts/` referenced the page, so a role added to a workspace JSON
left the published grant table quietly wrong — the Salis and Habitat rows had
each drifted by two roles before this guard existed. A reader treating the table
as the access-control record was reading a stale one.

The parsers take their roots as arguments so the falsifiability class below can
point them at a temporary tree: proving the comparison reports an added role
must not require editing a shipped workspace JSON.

Run standalone:  python3 -m unittest tests.test_workspace_doc_parity -v
"""

import glob
import json
import os
import re
import shutil
import tempfile
import unittest

APP_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
REPO_ROOT = os.path.dirname(APP_ROOT)
DESIGN_DOC = os.path.join(REPO_ROOT, "docs", "WORKSPACE-DESIGN.md")

# A Section 1 row: | **Label** | Module | Parent | `sequence_id` | Role, Role, ... |
DOC_ROW = re.compile(r"^\|\s*\*\*(?P<label>[^*]+)\*\*\s*\|(?P<rest>.*)\|\s*$")
# The parent cell of a root workspace, e.g. "— (root)" or "— (root, `is_hidden`)".
ROOT_PARENT = re.compile(r"^—\s*\(root")


def _cell(text):
    """A Markdown cell without its code ticks or padding."""
    return text.replace("`", "").strip()


def documented_rows(path=DESIGN_DOC):
    """{label: row} parsed from the Section 1 workspace table."""
    rows = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            match = DOC_ROW.match(line.rstrip("\n"))
            if not match:
                continue
            cells = [_cell(cell) for cell in match.group("rest").split("|")]
            if len(cells) != 4:
                continue
            module, parent, sequence_id, roles = cells
            rows[match.group("label").strip()] = {
                "module": module,
                "parent": "" if ROOT_PARENT.match(parent) else parent,
                "parent_cell": parent,
                "sequence_id": sequence_id,
                "roles": {role.strip() for role in roles.split(",") if role.strip()},
            }
    return rows


def shipped_workspaces(root=APP_ROOT):
    """{label: record} for every is_standard Workspace JSON under `root`."""
    out = {}
    for path in glob.glob(os.path.join(root, "*", "workspace", "*", "*.json")):
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict) or data.get("doctype") != "Workspace":
            continue
        out[data.get("label") or data.get("name")] = {
            "module": data.get("module") or "",
            "parent": (data.get("parent_page") or "").strip(),
            "sequence_id": data.get("sequence_id"),
            "roles": {
                row.get("role") for row in (data.get("roles") or []) if row.get("role")
            },
            "is_hidden": bool(data.get("is_hidden")),
            "path": os.path.relpath(path, os.path.dirname(root)),
        }
    return out


def role_mismatches(documented, shipped):
    """Human-readable diff of the role grants both sides claim, for shared labels."""
    report = []
    for label in sorted(set(documented) & set(shipped)):
        doc_roles = documented[label]["roles"]
        json_roles = shipped[label]["roles"]
        if doc_roles == json_roles:
            continue
        report.append(
            "{} ({}): undocumented grant {} · documented but not granted {}".format(
                label,
                shipped[label]["path"],
                sorted(json_roles - doc_roles) or "—",
                sorted(doc_roles - json_roles) or "—",
            )
        )
    return report


class TestWorkspaceDocParity(unittest.TestCase):
    def setUp(self):
        self.documented = documented_rows()
        self.shipped = shipped_workspaces()

    def test_both_sides_were_actually_parsed(self):
        """Non-vacuity: a broken table regex or glob would agree on two empty sets."""
        self.assertGreaterEqual(
            len(self.documented), 5, "Section 1 table did not parse — regex broke"
        )
        self.assertGreaterEqual(
            len(self.shipped), 5, "workspace JSON scan found nothing — glob broke"
        )
        for label in ("Salis", "Habitat"):
            self.assertIn(label, self.documented)
            self.assertIn(label, self.shipped)
            self.assertTrue(self.shipped[label]["roles"], f"{label} parsed with no roles")

    def test_documented_workspace_set_matches_disk(self):
        self.assertEqual(
            sorted(self.documented),
            sorted(self.shipped),
            "Section 1 lists a different set of workspaces than apex ships",
        )

    def test_documented_roles_match_the_workspace_json(self):
        """A role grant cannot change without this published table changing with it."""
        mismatches = role_mismatches(self.documented, self.shipped)
        self.assertEqual(
            mismatches,
            [],
            "docs/WORKSPACE-DESIGN.md Section 1 misstates who a workspace is "
            f"granted to: {mismatches}",
        )

    def test_documented_module_parent_and_sequence_match(self):
        offenders = []
        for label in sorted(set(self.documented) & set(self.shipped)):
            doc, live = self.documented[label], self.shipped[label]
            if doc["module"] != live["module"]:
                offenders.append(f"{label}: module {doc['module']!r} != {live['module']!r}")
            if doc["parent"] != live["parent"]:
                offenders.append(f"{label}: parent {doc['parent']!r} != {live['parent']!r}")
            if float(doc["sequence_id"]) != float(live["sequence_id"]):
                offenders.append(
                    f"{label}: sequence_id {doc['sequence_id']} != {live['sequence_id']}"
                )
        self.assertEqual(offenders, [], f"Section 1 identity columns are stale: {offenders}")

    def test_hidden_workspaces_are_flagged_in_the_table(self):
        """`is_hidden` is why a workspace is absent from the sidebar; the table
        annotates it, so the annotation has to track the JSON flag."""
        offenders = []
        for label in sorted(set(self.documented) & set(self.shipped)):
            annotated = "is_hidden" in self.documented[label]["parent_cell"]
            if annotated != self.shipped[label]["is_hidden"]:
                offenders.append(f"{label}: table says is_hidden={annotated}")
        self.assertEqual(offenders, [], f"is_hidden annotation is stale: {offenders}")


class TestParityGuardIsFalsifiable(unittest.TestCase):
    """The comparison must actually report a changed grant.

    Proven against a temporary copy of the real document and a real workspace
    JSON rather than by editing the shipped file: a proof that mutates tracked
    state is one revert away from corrupting the tree it is proving.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.doc_copy = os.path.join(self.tmp, "WORKSPACE-DESIGN.md")
        shutil.copyfile(DESIGN_DOC, self.doc_copy)
        self.pkg = os.path.join(self.tmp, "pkg")
        source = os.path.join(APP_ROOT, "salis", "workspace", "salis")
        shutil.copytree(source, os.path.join(self.pkg, "salis", "workspace", "salis"))

    def _salis_json(self):
        return os.path.join(self.pkg, "salis", "workspace", "salis", "salis.json")

    def _compare(self):
        documented = documented_rows(self.doc_copy)
        shipped = shipped_workspaces(self.pkg)
        self.assertIn("Salis", shipped, "fixture workspace did not parse")
        return role_mismatches(documented, shipped)

    def test_the_unmodified_copy_agrees(self):
        self.assertEqual(self._compare(), [], "baseline fixture must start clean")

    def test_a_role_added_to_the_workspace_json_is_reported(self):
        path = self._salis_json()
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        data["roles"].append({"role": "Accommodation Manager"})
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh)

        mismatches = self._compare()
        self.assertEqual(len(mismatches), 1, f"added grant went unreported: {mismatches}")
        self.assertIn("Accommodation Manager", mismatches[0])

    def test_a_role_dropped_from_the_document_is_reported(self):
        with open(self.doc_copy, encoding="utf-8") as fh:
            text = fh.read()
        edited = text.replace(
            "Fleet Supervisor, Government Relations Officer", "Fleet Supervisor", 1
        )
        self.assertNotEqual(edited, text, "Salis row no longer matches the edit pattern")
        with open(self.doc_copy, "w", encoding="utf-8") as fh:
            fh.write(edited)

        mismatches = self._compare()
        self.assertEqual(len(mismatches), 1, f"dropped row entry went unreported: {mismatches}")
        self.assertIn("Government Relations Officer", mismatches[0])


if __name__ == "__main__":
    unittest.main()
