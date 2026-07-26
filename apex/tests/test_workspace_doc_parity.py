# Copyright (c) 2026, AFMCO and contributors
"""docs/WORKSPACE-DESIGN.md must match the shipped Workspace JSON.

Two published tables on that page describe shipped JSON, and both are derived
from it here rather than maintained by hand.

Section 1 states, per workspace, the module that owns it, where it sits in the
sidebar, and the exact list of roles it grants. Nothing under `apex/` or
`scripts/` referenced the page, so a role added to a workspace JSON left the
published grant table quietly wrong — the Salis and Habitat rows had each
drifted by two roles before this guard existed. A reader treating the table as
the access-control record was reading a stale one.

Section 3's portal-shortcut table states, per portal shortcut, its label, its
URL, and the workspace it sits on. It was NOT derived when the Section 1 role
table was, and it drifted for exactly that reason: the Fleet shortcut was
renamed `Fleet Portal` -> `Fleet OS` and a `Masar Supervisor` shortcut was added,
while the guarded role table stayed correct throughout. Deriving one table and
not its neighbour is what let that ship, so both are derived now.

Two shipped-JSON facts shape the shortcut check:

- A shortcut renders only when its `shortcuts[]` row label and the matching
  `content` block's `shortcut_name` agree. A disagreement is not cosmetic — the
  block silently renders nothing — so it fails here on its own.
- The comparison runs in BOTH directions. A guard that only checks
  documented-implies-shipped lets a new undocumented shortcut through in
  silence, which is the exact shape of the drift this file exists to stop.

The parsers take their roots as arguments so the falsifiability classes below
can point them at a temporary tree: proving the comparison reports an added role
or a renamed shortcut must not require editing a shipped workspace JSON.

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
# A Section 3 portal row: | Workspace | `Label` | `/route` | prose |
# The backticked, slash-leading URL cell is what separates it from the other
# four-column tables on the page, which carry no such cell.
PORTAL_ROW = re.compile(
    r"^\|\s*(?P<workspace>[^|`*]+?)\s*"
    r"\|\s*`(?P<label>[^`|]+)`\s*"
    r"\|\s*`(?P<url>/[^`|]*)`\s*"
    r"\|(?P<portal>[^|]*)\|\s*$"
)


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


def _content_shortcut_names(data):
    """The `shortcut_name` of every shortcut block in a workspace's `content` string."""
    try:
        blocks = json.loads(data.get("content") or "[]")
    except (json.JSONDecodeError, TypeError):
        return []
    return [
        (block.get("data") or {}).get("shortcut_name")
        for block in blocks
        if isinstance(block, dict) and block.get("type") == "shortcut"
    ]


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
            "shortcuts": [row for row in (data.get("shortcuts") or []) if isinstance(row, dict)],
            "content_shortcut_names": _content_shortcut_names(data),
            "path": os.path.relpath(path, os.path.dirname(root)),
        }
    return out


def documented_portal_shortcuts(path=DESIGN_DOC):
    """{(workspace, label): url} parsed from the Section 3 portal-shortcut table."""
    rows = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            match = PORTAL_ROW.match(line.rstrip("\n"))
            if not match:
                continue
            key = (match.group("workspace").strip(), match.group("label").strip())
            rows[key] = match.group("url").strip()
    return rows


def is_portal_route(url):
    """A site-root route served outside the Desk.

    `/app/...` is a Desk route that merely ships as a URL shortcut (Housing's
    `Front Desk` and `Arrivals Desk`), and `//host/...` is protocol-relative,
    i.e. off-site. Neither is a portal, so neither belongs in the doc table.
    """
    url = (url or "").strip()
    return url.startswith("/") and not url.startswith("//") and not url.startswith("/app/")


def shipped_portal_shortcuts(shipped):
    """{(workspace, label): url} for every portal shortcut in the shipped JSON."""
    rows = {}
    for label, record in shipped.items():
        for row in record["shortcuts"]:
            if row.get("type") != "URL" or not is_portal_route(row.get("url")):
                continue
            rows[(label, (row.get("label") or "").strip())] = (row.get("url") or "").strip()
    return rows


def portal_shortcut_mismatches(documented, shipped):
    """Both-direction diff of the portal shortcuts the doc and the JSON each claim."""
    report = []
    for workspace, label in sorted(set(documented) - set(shipped)):
        report.append(
            f"{workspace}: documented shortcut {label!r} ships on no workspace JSON"
        )
    for key in sorted(set(shipped) - set(documented)):
        report.append(
            f"{key[0]}: shortcut {key[1]!r} -> {shipped[key]} ships but is undocumented"
        )
    for key in sorted(set(documented) & set(shipped)):
        if documented[key] != shipped[key]:
            report.append(
                f"{key[0]}: shortcut {key[1]!r} documented as {documented[key]} "
                f"but ships as {shipped[key]}"
            )
    return report


def shortcut_block_mismatches(shipped):
    """Shortcut rows whose `content` block does not name them, and the reverse.

    A workspace renders a shortcut only when the `shortcuts[]` row label and the
    content block's `shortcut_name` are the same string, so either half alone is
    a shortcut that does not appear on the page.
    """
    report = []
    for label in sorted(shipped):
        record = shipped[label]
        rows = {(row.get("label") or "").strip() for row in record["shortcuts"]}
        blocks = {(name or "").strip() for name in record["content_shortcut_names"]}
        if rows == blocks:
            continue
        report.append(
            "{} ({}): shortcut row with no content block {} · content block with "
            "no shortcut row {}".format(
                label,
                record["path"],
                sorted(rows - blocks) or "—",
                sorted(blocks - rows) or "—",
            )
        )
    return report


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

    def test_both_shortcut_sides_were_actually_parsed(self):
        """Non-vacuity for the shortcut check: two empty sets always agree."""
        documented = documented_portal_shortcuts()
        shipped = shipped_portal_shortcuts(self.shipped)
        self.assertGreaterEqual(
            len(documented), 5, "Section 3 portal table did not parse — regex broke"
        )
        self.assertGreaterEqual(
            len(shipped), 5, "no portal shortcut found in the workspace JSON"
        )
        self.assertTrue(
            any(record["content_shortcut_names"] for record in self.shipped.values()),
            "no content shortcut block parsed — the content JSON is not being read",
        )

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

    def test_documented_portal_shortcuts_match_the_workspace_json(self):
        """A portal shortcut cannot be added, renamed, retargeted, or removed
        without Section 3's table changing with it — in either direction."""
        mismatches = portal_shortcut_mismatches(
            documented_portal_shortcuts(), shipped_portal_shortcuts(self.shipped)
        )
        self.assertEqual(
            mismatches,
            [],
            "docs/WORKSPACE-DESIGN.md Section 3 misstates the shipped portal "
            f"shortcuts: {mismatches}",
        )

    def test_every_shortcut_row_has_a_matching_content_block(self):
        """Row label and block `shortcut_name` must agree or nothing renders."""
        mismatches = shortcut_block_mismatches(self.shipped)
        self.assertEqual(
            mismatches, [], f"shortcut rows and content blocks disagree: {mismatches}"
        )

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


class TestShortcutParityGuardIsFalsifiable(unittest.TestCase):
    """The shortcut comparison must report drift in BOTH directions.

    The whole point of this guard is the direction the old one lacked: a new
    shortcut nobody documented has to fail, not just a documented one that
    stopped shipping. Both are proven here, against a temporary mirror of the
    real page and the real workspace tree rather than by editing shipped files.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.doc_copy = os.path.join(self.tmp, "WORKSPACE-DESIGN.md")
        shutil.copyfile(DESIGN_DOC, self.doc_copy)
        self.pkg = os.path.join(self.tmp, "pkg")
        # The whole workspace tree, so the both-directions comparison stays strict:
        # a partial mirror would report every unmirrored workspace as missing.
        for module in ("habitat", "salis"):
            shutil.copytree(
                os.path.join(APP_ROOT, module, "workspace"),
                os.path.join(self.pkg, module, "workspace"),
            )

    def _fleet_json(self):
        return os.path.join(self.pkg, "salis", "workspace", "fleet", "fleet.json")

    def _edit_fleet(self, mutate):
        path = self._fleet_json()
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        mutate(data)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh)

    def _add_content_shortcut(self, data, name):
        blocks = json.loads(data["content"])
        blocks.append({"id": name, "type": "shortcut", "data": {"shortcut_name": name, "col": 3}})
        data["content"] = json.dumps(blocks)

    def _compare(self):
        shipped = shipped_workspaces(self.pkg)
        self.assertIn("Fleet", shipped, "fixture workspace tree did not parse")
        return portal_shortcut_mismatches(
            documented_portal_shortcuts(self.doc_copy), shipped_portal_shortcuts(shipped)
        )

    def test_the_unmodified_copy_agrees(self):
        self.assertEqual(self._compare(), [], "baseline fixture must start clean")
        self.assertEqual(shortcut_block_mismatches(shipped_workspaces(self.pkg)), [])

    def test_a_wrong_label_in_the_document_is_reported(self):
        """The drift this guard was written for: a shortcut renamed in the JSON
        while the published table kept the old label."""
        with open(self.doc_copy, encoding="utf-8") as fh:
            text = fh.read()
        edited = text.replace("| Fleet | `Fleet OS` |", "| Fleet | `Fleet Portal` |", 1)
        self.assertNotEqual(edited, text, "Fleet portal row no longer matches the edit pattern")
        with open(self.doc_copy, "w", encoding="utf-8") as fh:
            fh.write(edited)

        mismatches = self._compare()
        self.assertEqual(len(mismatches), 2, f"renamed label went unreported: {mismatches}")
        self.assertTrue(any("Fleet Portal" in line for line in mismatches))
        self.assertTrue(any("Fleet OS" in line and "undocumented" in line for line in mismatches))

    def test_an_undocumented_shipped_shortcut_is_reported(self):
        """The direction a documented-implies-shipped guard misses entirely."""
        self._edit_fleet(
            lambda data: data["shortcuts"].append(
                {"type": "URL", "label": "Ghost Portal", "url": "/ghost"}
            )
        )

        mismatches = self._compare()
        self.assertEqual(len(mismatches), 1, f"new shortcut went unreported: {mismatches}")
        self.assertIn("Ghost Portal", mismatches[0])
        self.assertIn("undocumented", mismatches[0])

    def test_a_retargeted_shortcut_is_reported(self):
        """Same label, different URL — the table's URL column is load-bearing."""
        def retarget(data):
            for row in data["shortcuts"]:
                if row.get("label") == "Fleet OS":
                    row["url"] = "/fleet"

        self._edit_fleet(retarget)
        mismatches = self._compare()
        self.assertEqual(len(mismatches), 1, f"retarget went unreported: {mismatches}")
        self.assertIn("/fleet-os", mismatches[0])
        self.assertIn("/fleet", mismatches[0])

    def test_a_shortcut_row_without_its_content_block_is_reported(self):
        """A row the content never names renders nothing, so it fails on its own."""
        self._edit_fleet(
            lambda data: data["shortcuts"].append(
                {"type": "DocType", "label": "Orphan Row", "link_to": "Salis Vehicle"}
            )
        )
        mismatches = shortcut_block_mismatches(shipped_workspaces(self.pkg))
        self.assertEqual(len(mismatches), 1, f"orphan row went unreported: {mismatches}")
        self.assertIn("Orphan Row", mismatches[0])

    def test_a_documented_new_portal_shortcut_stays_green(self):
        """The lookalike: the same shape of change as the failures above, done
        correctly. Adding a portal shortcut AND its table row must not fail, or
        the guard would just be blocking new shortcuts."""
        def add(data):
            data["shortcuts"].append(
                {"type": "URL", "label": "Depot Board", "url": "/depot", "color": "Green"}
            )
            self._add_content_shortcut(data, "Depot Board")

        self._edit_fleet(add)
        with open(self.doc_copy, encoding="utf-8") as fh:
            text = fh.read()
        edited = text.replace(
            "| Fleet | `Masar Supervisor` | `/masar-supervisor` |",
            "| Fleet | `Depot Board` | `/depot` | Depot board |\n"
            "| Fleet | `Masar Supervisor` | `/masar-supervisor` |",
            1,
        )
        self.assertNotEqual(edited, text, "Masar row no longer matches the edit pattern")
        with open(self.doc_copy, "w", encoding="utf-8") as fh:
            fh.write(edited)

        self.assertEqual(self._compare(), [], "a correctly documented shortcut must stay green")
        self.assertEqual(shortcut_block_mismatches(shipped_workspaces(self.pkg)), [])

    def test_a_desk_url_shortcut_is_not_treated_as_a_portal(self):
        """Housing's `/app/front-desk` shortcuts are URL-typed Desk links. If the
        classifier counted them, every one would read as undocumented drift."""
        self.assertFalse(is_portal_route("/app/front-desk"))
        self.assertFalse(is_portal_route("//evil.example/x"))
        self.assertFalse(is_portal_route("https://example.com"))
        self.assertTrue(is_portal_route("/fleet-os"))
        shipped = shipped_portal_shortcuts(shipped_workspaces(self.pkg))
        self.assertNotIn(("Housing", "Front Desk"), shipped)
        self.assertIn(("Housing", "Housing Portal"), shipped)


if __name__ == "__main__":
    unittest.main()
