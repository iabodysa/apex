# Copyright (c) 2026, AFMCO and contributors
"""Every published table that describes shipped code is derived from it here.

Three GitHub-public documents state facts about the shipped tree, and each one
had already drifted before a guard read it: docs/WORKSPACE-DESIGN.md (workspace
roles, portal shortcuts), README.md (the served portal routes), and
docs/training/README.md (the declared modules). A published claim with nothing
deriving it goes stale silently — the suite stays green while the document that
represents the app on GitHub is wrong — so all three are derived in one place.

docs/WORKSPACE-DESIGN.md must match the shipped Workspace JSON.

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

README.md's "Served portal routes" table states, per route, the audience, the
authentication path — guest redirect or guest-accessible, and the role set the
page applies — and the backing controller and bundle. It was the last public
description of routing with nothing deriving it: the two neighbouring guards
(test_portal_route_coverage, test_apps_screen_gate_wiring) compare code against
code and never open the README. That is the same gap that let the workspace
shortcut table above drift. The route side is now read from the shipped `www`
tree, and the count sentence over the table is derived from it too.

The role gate is read from what `get_context()` APPLIES, never from what the
module defines. www/fleet.py defines FLEET_ROLES and consults it only in its
/apps tile helper while gating on nothing, so a module-level scan would publish
/fleet as role-gated. /fleet and /fleet-os differ in controller, bundle and
gate, so swapping the two rows fails on all three.

docs/training/README.md's opening states how many names `apex/modules.txt`
declares and lists one bullet per module. It said FIVE, describing a SIM
Operations module whose package no longer exists — true when written, false
after the fold, and green the whole time. The count and the bullet set are both
derived from modules.txt now, and README.md's own module bullets with them.

docs/training/settings.md carried the same defect one page over: its desk-page
note said Telecom Control's module "ships alongside Habitat, Salis, Apex Core,
and SIM Operations", naming the retired module as still shipping. The
derivation above covered the other two documents and stopped short of this one,
so this page kept a module claim that nothing checked. It is covered here. The
page states its module set as one bolded sentence rather than as bullets, so it
gets its own parser, then the same both-direction comparison and the same count
check as the other two.

`SIM Operations User` is a live ROLE (apex/setup.py) held by the Custody and
Habitat workspaces, the Telecom Control page and the telecom reports. It merely
reads like the retired module. Nothing here derives roles from module names, so
that the next reader of this file does not "finish the job" by deleting it.

The parsers take their roots as arguments so the falsifiability classes below
can point them at a temporary tree: proving the comparison reports an added role,
a renamed shortcut, a retired route or a new module must not require editing a
shipped file.

Run standalone:  python3 -m unittest apex.tests.test_workspace_doc_parity -v
"""

import ast
import glob
import json
import os
import re
import shutil
import tempfile
import unittest

APP_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
APP_PKG = os.path.basename(APP_ROOT)
REPO_ROOT = os.path.dirname(APP_ROOT)
DESIGN_DOC = os.path.join(REPO_ROOT, "docs", "WORKSPACE-DESIGN.md")
README = os.path.join(REPO_ROOT, "README.md")
TRAINING_DOC = os.path.join(REPO_ROOT, "docs", "training", "README.md")
SETTINGS_DOC = os.path.join(REPO_ROOT, "docs", "training", "settings.md")
WWW_ROOT = os.path.join(APP_ROOT, "www")
MODULES_TXT = os.path.join(APP_ROOT, "modules.txt")

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


NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
}

# A portal shell mounts its SPA as /assets/<app>/<bundle>/assets/index.js. A www
# page without one is not a portal route (the /housing-count redirect marker).
SHELL_BUNDLE = re.compile(r'src="/assets/' + APP_PKG + r'/([A-Za-z0-9_]+)/assets/index\.js"')

# A route row: | `/route` | audience | authentication path | `controller` · `bundle` |
ROUTE_ROW = re.compile(
    r"^\|\s*`(?P<route>/[a-z0-9-]+)`\s*"
    r"\|(?P<audience>[^|]*)"
    r"\|(?P<gate>[^|]*)"
    r"\|(?P<backing>[^|]*)\|\s*$"
)
# The machine-readable half of a gate cell: the controller's role constant, then a
# colon, then the roles, then a period. Prose may sit on either side of it.
GATE_SPEC = re.compile(r"`(?P<const>[A-Z][A-Z0-9_]*_ROLES)`:\s*(?P<roles>[^.|]+)\.")
BACKING_CELL = re.compile(r"^`(?P<controller>[^`]+)`\s*·\s*`(?P<bundle>[^`]+)`$")
GUEST_MARKER = "Guest-accessible"
SESSION_MARKER = "Guest redirect"

ROUTE_COUNT = re.compile(r"serves \*\*(?P<count>[a-z]+)\*\* portal routes")
SESSION_SENTENCE = re.compile(
    r"The \*\*(?P<count>[a-z]+)\*\* session-gated operator portals"
    r"(?P<body>.*?)do not yet have training pages"
)
INLINE_ROUTE = re.compile(r"`(/[a-z0-9-]+)`")

MODULE_COUNT = re.compile(
    r"`" + APP_PKG + r"/modules\.txt` declares \*\*(?P<count>[a-z]+)\*\* names"
)
MODULE_BULLET = re.compile(r"^-\s+\*\*(?P<name>[^*]+)\*\*")
README_MODULE_ANCHOR = re.compile(r"^## Modules\s*$")
TRAINING_MODULE_ANCHOR = re.compile(r"one per bullet below:")

BOLD = re.compile(r"\*\*([^*]+)\*\*")
# settings.md names its modules in one sentence rather than as bullets: the same
# count phrase the other two documents use, an em dash, then every declared name
# in bold up to the sentence's period. Anchored on that sentence and not scanned
# file-wide, because the same blockquote bolds three desk-page names as well.
SETTINGS_MODULE_SENTENCE = re.compile(
    r"`" + APP_PKG + r"/modules\.txt` declares \*\*[a-z]+\*\* names\s*—(?P<names>[^.]+)\."
)


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _flat(text):
    """One-line view of a document, so a sentence check survives Markdown wrapping."""
    return re.sub(r"\s+", " ", text)


def _prose(text):
    """`_flat` with Markdown blockquote markers dropped.

    settings.md states its module set inside a `>` blockquote, so every wrap
    point injects a `>` mid-sentence. Stripping the markers first makes the
    parse independent of where the paragraph happens to wrap.
    """
    return _flat(re.sub(r"^\s*>\s?", "", text, flags=re.MULTILINE))


def _number(word):
    return NUMBER_WORDS.get((word or "").lower())


def _module_level_role_sets(tree):
    """{NAME: frozenset(roles)} for every module-level `NAME = {"Role", ...}`."""
    found = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Set):
            continue
        members = {
            element.value
            for element in node.value.elts
            if isinstance(element, ast.Constant) and isinstance(element.value, str)
        }
        if len(members) != len(node.value.elts):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                found[target.id] = frozenset(members)
    return found


def _calls(node, name):
    """True when `name(...)` is called anywhere inside `node`."""
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        func = child.func
        called = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
        if called == name:
            return True
    return False


def controller_gate(source):
    """(session_gated, applied constants, roles) read from a controller's get_context().

    Only a constant get_context() itself reads counts as a gate: www/fleet.py
    defines FLEET_ROLES and consults it solely in the /apps tile helper while
    gating on nothing, so a module-level scan would publish /fleet as gated.
    """
    tree = ast.parse(source)
    constants = _module_level_role_sets(tree)
    context = next(
        (n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "get_context"),
        None,
    )
    if context is None:
        return None, (), frozenset()
    applied = sorted(
        {n.id for n in ast.walk(context) if isinstance(n, ast.Name) and n.id in constants}
    )
    roles = frozenset().union(*(constants[name] for name in applied)) if applied else frozenset()
    return _calls(context, "guest_redirect"), tuple(applied), roles


def shipped_portal_routes(www_root=WWW_ROOT):
    """{route: record} for every www shell that mounts a portal bundle."""
    routes = {}
    for shell in sorted(glob.glob(os.path.join(www_root, "*.html"))):
        bundles = SHELL_BUNDLE.findall(_read(shell))
        if not bundles:
            continue
        stem = os.path.basename(shell)[: -len(".html")]
        # Frappe resolves a www controller by swapping hyphens for underscores.
        module = stem.replace("-", "_")
        path = os.path.join(www_root, module + ".py")
        gate = controller_gate(_read(path)) if os.path.isfile(path) else (None, (), frozenset())
        routes["/" + stem] = {
            "controller": f"{APP_PKG}/www/{module}.py" if os.path.isfile(path) else None,
            "bundle": bundles[0],
            "session_gated": gate[0],
            "constants": gate[1],
            "roles": gate[2],
        }
    return routes


def documented_portal_routes(path=README):
    """{route: record} parsed from the README's served-portal-routes table."""
    rows = {}
    for line in _read(path).splitlines():
        match = ROUTE_ROW.match(line)
        if not match:
            continue
        gate, backing = match.group("gate"), match.group("backing").strip()
        specs = GATE_SPEC.findall(gate)
        cell = BACKING_CELL.match(backing)
        guest, session = GUEST_MARKER in gate, SESSION_MARKER in gate
        rows[match.group("route")] = {
            "controller": cell.group("controller").strip() if cell else None,
            "bundle": cell.group("bundle").strip() if cell else None,
            # Neither marker, or both, is an unreadable cell — reported, not guessed.
            "session_gated": session if guest != session else None,
            "constants": tuple(const for const, _ in specs),
            "roles": frozenset(
                role.strip() for _, roles in specs for role in roles.split(",") if role.strip()
            ),
        }
    return rows


def _show(value):
    if isinstance(value, (frozenset, set)):
        return sorted(value) or "none"
    if isinstance(value, tuple):
        return list(value) or "none"
    return value


ROUTE_FIELDS = (
    ("controller", "backing controller"),
    ("bundle", "bundle"),
    ("session_gated", "guest-redirect gate"),
    ("constants", "role constant"),
    ("roles", "gated roles"),
)


def portal_route_mismatches(documented, shipped):
    """Both-direction diff of the routes the README and the www tree each claim."""
    report = []
    for route in sorted(set(documented) - set(shipped)):
        report.append(f"{route}: documented in the README but no www shell serves it")
    for route in sorted(set(shipped) - set(documented)):
        report.append(
            f"{route}: served by {shipped[route]['controller'] or 'no controller'} "
            "but the README table omits it"
        )
    for route in sorted(set(documented) & set(shipped)):
        doc, live = documented[route], shipped[route]
        for key, label in ROUTE_FIELDS:
            if doc[key] != live[key]:
                report.append(
                    f"{route}: {label} documented as {_show(doc[key])} "
                    f"but ships as {_show(live[key])}"
                )
    return report


def documented_route_count(path):
    """The bolded number word in "Apex serves **N** portal routes"."""
    match = ROUTE_COUNT.search(_flat(_read(path)))
    return _number(match.group("count")) if match else None


def documented_session_gated(path=TRAINING_DOC):
    """(count, routes) from the training guide's session-gated portals note."""
    match = SESSION_SENTENCE.search(_flat(_read(path)))
    if not match:
        return None, frozenset()
    return _number(match.group("count")), frozenset(INLINE_ROUTE.findall(match.group("body")))


def declared_modules(path=MODULES_TXT):
    """modules.txt as frappe.get_file_items reads it: stripped, blank and # lines dropped."""
    lines = [line.strip() for line in _read(path).splitlines()]
    return [line for line in lines if line and not line.startswith("#")]


def documented_module_count(path=TRAINING_DOC):
    # _prose, not _flat: settings.md's count sentence sits in a blockquote.
    match = MODULE_COUNT.search(_prose(_read(path)))
    return _number(match.group("count")) if match else None


def documented_settings_modules(path=SETTINGS_DOC):
    """The bolded module names in settings.md's declared-modules sentence."""
    match = SETTINGS_MODULE_SENTENCE.search(_prose(_read(path)))
    return [name.strip() for name in BOLD.findall(match.group("names"))] if match else []


def documented_modules(path, anchor):
    """Bolded bullet names in the first bullet run after `anchor`.

    Anchored rather than file-wide: both documents carry other bolded bullet
    lists further down, and only the run under the anchor is the module list.
    """
    names, started = [], False
    for line in _read(path).splitlines():
        if not started:
            started = bool(anchor.search(line))
            continue
        bullet = MODULE_BULLET.match(line)
        if bullet:
            names.append(bullet.group("name").strip())
        elif names and not line.startswith("  "):
            break
    return names


def module_doc_mismatches(declared, documented, count=None):
    """Both-direction diff of the modules a document lists against modules.txt."""
    report = []
    for name in sorted(set(documented) - set(declared)):
        report.append(f"{name!r}: the document lists it but modules.txt does not declare it")
    for name in sorted(set(declared) - set(documented)):
        report.append(f"{name!r}: modules.txt declares it but the document lists no bullet")
    if count is not None and count != len(declared):
        report.append(
            f"the document says modules.txt declares {count} names; it declares {len(declared)}"
        )
    return report


class TestPortalRouteDocParity(unittest.TestCase):
    """README.md's route table must be what apex/www/ actually serves."""

    def setUp(self):
        self.documented = documented_portal_routes()
        self.shipped = shipped_portal_routes()

    def test_both_sides_were_actually_parsed(self):
        """Non-vacuity: a broken row regex or shell glob would agree on two empty sets."""
        self.assertGreaterEqual(
            len(self.documented), 5, "the README route table did not parse — regex broke"
        )
        self.assertGreaterEqual(
            len(self.shipped), 5, "the www shell scan found nothing — glob broke"
        )
        gated = [route for route, row in self.shipped.items() if row["roles"]]
        self.assertTrue(gated, "no controller parsed with a role gate — the AST read broke")
        self.assertTrue(
            all(row["bundle"] for row in self.shipped.values()), "a shell parsed with no bundle"
        )

    def test_the_table_matches_the_shipped_www_tree(self):
        """A route, controller, bundle or gate cannot change without this table."""
        mismatches = portal_route_mismatches(self.documented, self.shipped)
        self.assertEqual(
            mismatches,
            [],
            "README.md's served-portal-routes table misstates the shipped www tree. "
            "A gated row names its controller's role constant in backticks, then a "
            f"colon, then the comma-separated roles, then a period: {mismatches}",
        )

    def test_the_published_route_count_is_the_shipped_count(self):
        """The count sentence is a claim about the same directory as the table."""
        for path in (README, TRAINING_DOC):
            with self.subTest(document=os.path.relpath(path, REPO_ROOT)):
                self.assertEqual(
                    documented_route_count(path),
                    len(self.shipped),
                    "the published portal-route count is not the number of served routes",
                )

    def test_the_training_guide_names_the_session_gated_portals(self):
        """The guide's note is the other published list of the same routes."""
        count, named = documented_session_gated()
        derived = frozenset(r for r, row in self.shipped.items() if row["session_gated"])
        self.assertEqual(
            named,
            derived,
            "docs/training/README.md names a different set of session-gated portals "
            "than the www controllers redirect guests from",
        )
        self.assertEqual(count, len(derived), "the note's count is not the derived count")


class TestModuleDocParity(unittest.TestCase):
    """Every public document that names the module set must match modules.txt."""

    def setUp(self):
        self.declared = declared_modules()

    def test_the_registry_read_is_non_vacuous(self):
        self.assertIn("Habitat", self.declared, "modules.txt read found no Habitat — parser broke")

    def test_the_training_guide_matches_modules_txt(self):
        documented = documented_modules(TRAINING_DOC, TRAINING_MODULE_ANCHOR)
        self.assertTrue(documented, "the training guide's module bullets did not parse")
        mismatches = module_doc_mismatches(
            self.declared, documented, documented_module_count(TRAINING_DOC)
        )
        self.assertEqual(
            mismatches, [], f"docs/training/README.md misstates the declared modules: {mismatches}"
        )

    def test_the_readme_module_section_matches_modules_txt(self):
        documented = documented_modules(README, README_MODULE_ANCHOR)
        self.assertTrue(documented, "the README's module bullets did not parse")
        mismatches = module_doc_mismatches(self.declared, documented)
        self.assertEqual(
            mismatches, [], f"README.md's Modules section misstates the declared modules: {mismatches}"
        )

    def test_the_settings_page_matches_modules_txt(self):
        """The desk-page note names the module set too, in prose rather than bullets.

        It is the page that said the set "ships alongside ... SIM Operations"
        after that module was folded away — the A-208 defect this covers.
        """
        documented = documented_settings_modules()
        self.assertTrue(
            documented,
            "settings.md's declared-modules sentence did not parse — reword it to keep "
            "the count phrase, an em dash, then every module name in bold",
        )
        mismatches = module_doc_mismatches(
            self.declared, documented, documented_module_count(SETTINGS_DOC)
        )
        self.assertEqual(
            mismatches,
            [],
            f"docs/training/settings.md misstates the declared modules: {mismatches}",
        )


class TestPortalRouteGuardIsFalsifiable(unittest.TestCase):
    """The route comparison must report drift in BOTH directions.

    Proven against a temporary mirror of the README and the whole www tree: a
    proof that mutates a shipped shell or controller to make its point is one
    failed revert away from corrupting the tree it is proving.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.readme = os.path.join(self.tmp, "README.md")
        shutil.copyfile(README, self.readme)
        self.www = os.path.join(self.tmp, "www")
        shutil.copytree(WWW_ROOT, self.www)

    def _compare(self):
        shipped = shipped_portal_routes(self.www)
        self.assertIn("/fleet-os", shipped, "fixture www tree did not parse")
        return portal_route_mismatches(documented_portal_routes(self.readme), shipped)

    def _edit_readme(self, old, new):
        text = _read(self.readme)
        edited = text.replace(old, new, 1)
        self.assertNotEqual(edited, text, f"README copy no longer contains {old!r}")
        with open(self.readme, "w", encoding="utf-8") as fh:
            fh.write(edited)

    def _plant_route(self, route, bundle="depot_portal"):
        """A shell that mounts a bundle plus its controller — a served portal route."""
        shell = f'<div id="app"></div>\n<script src="/assets/{APP_PKG}/{bundle}/assets/index.js">'
        with open(os.path.join(self.www, route + ".html"), "w", encoding="utf-8") as fh:
            fh.write(shell + "</script>\n")
        controller = (
            '"""Planted portal."""\n\n'
            "from apex.apex_core.utils.portal_bootstrap import guest_redirect\n\n"
            'DEPOT_ROLES = {"System Manager", "Fleet Manager"}\n\n\n'
            "def get_context(context):\n"
            f'    guest_redirect("/{route}")\n'
            "    context.has_role = bool(DEPOT_ROLES & set(frappe.get_roles()))\n"
            "    return context\n"
        )
        with open(os.path.join(self.www, route.replace("-", "_") + ".py"), "w", encoding="utf-8") as fh:
            fh.write(controller)

    def test_the_unmodified_copy_agrees(self):
        self.assertEqual(self._compare(), [], "baseline fixture must start clean")

    def test_a_documented_route_that_no_longer_ships_is_reported(self):
        """One direction: the table promises a route the www tree no longer serves."""
        self._edit_readme(
            "| `/safety` |",
            "| `/depot` | Depot staff | Guest redirect, then `DEPOT_ROLES`: System Manager. |"
            f" `{APP_PKG}/www/depot.py` · `depot_portal` |\n| `/safety` |",
        )
        mismatches = self._compare()
        self.assertEqual(len(mismatches), 1, f"retired route went unreported: {mismatches}")
        self.assertIn("/depot", mismatches[0])
        self.assertIn("no www shell serves it", mismatches[0])

    def test_a_shipped_route_the_table_omits_is_reported(self):
        """The direction a documented-implies-shipped guard misses entirely."""
        self._plant_route("ghost")
        mismatches = self._compare()
        self.assertEqual(len(mismatches), 1, f"new route went unreported: {mismatches}")
        self.assertIn("/ghost", mismatches[0])
        self.assertIn("omits it", mismatches[0])

    def test_a_role_added_to_a_gate_constant_is_reported(self):
        """The gate column is derived from get_context(), not from prose."""
        path = os.path.join(self.www, "safety.py")
        source = _read(path).replace(
            '"Resident Supervisor",', '"Resident Supervisor",\n    "Fleet Manager",', 1
        )
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(source)

        mismatches = self._compare()
        self.assertEqual(len(mismatches), 1, f"widened gate went unreported: {mismatches}")
        self.assertIn("/safety", mismatches[0])
        self.assertIn("Fleet Manager", mismatches[0])

    def test_a_retargeted_controller_or_bundle_is_reported(self):
        """The /fleet and /fleet-os pair differs by controller, bundle and gate, so
        swapping the two published rows fails on all three."""
        self._edit_readme(f"`{APP_PKG}/www/fleet_os.py` · `fleet_os_portal`", "`x/y.py` · `nope`")
        mismatches = self._compare()
        self.assertEqual(len(mismatches), 2, f"backing cell drift went unreported: {mismatches}")
        self.assertTrue(any("backing controller" in line for line in mismatches))
        self.assertTrue(any("bundle" in line for line in mismatches))

    def test_a_route_added_correctly_on_both_sides_stays_green(self):
        """The lookalike: the same change as the failures above, done on BOTH sides.
        It must pass, or the guard would just be blocking new portals."""
        self._plant_route("depot")
        self._edit_readme(
            "| `/safety` |",
            "| `/depot` | Depot staff | Guest redirect, then `DEPOT_ROLES`: System Manager,"
            f" Fleet Manager. | `{APP_PKG}/www/depot.py` · `depot_portal` |\n| `/safety` |",
        )
        self.assertEqual(self._compare(), [], "a correctly documented route must stay green")

        self._edit_readme("serves **seven** portal routes", "serves **eight** portal routes")
        self.assertEqual(documented_route_count(self.readme), len(shipped_portal_routes(self.www)))

    def test_a_constant_get_context_never_applies_is_not_a_gate(self):
        """The /fleet shape, on a source string so the proof cannot go stale: a page
        that defines a role set for its /apps tile while gating on nothing."""
        source = (
            'FLEET_ROLES = {"Fleet Manager"}\n\n\n'
            "def has_apps_screen_access():\n"
            "    return bool(FLEET_ROLES & set(frappe.get_roles()))\n\n\n"
            "def get_context(context):\n"
            '    guest_redirect("/fleet")\n'
            "    context.can_view = 1\n"
            "    return context\n"
        )
        self.assertEqual(controller_gate(source), (True, (), frozenset()))
        gated = source.replace("context.can_view = 1", "context.ok = bool(FLEET_ROLES)")
        self.assertEqual(controller_gate(gated), (True, ("FLEET_ROLES",), frozenset({"Fleet Manager"})))


class TestModuleDocGuardIsFalsifiable(unittest.TestCase):
    """The module comparison must report a modules.txt change the guide missed.

    Same temp-mirror technique: modules.txt is the register a fresh install turns
    into Module Def rows, so no proof may edit the shipped copy.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.modules = os.path.join(self.tmp, "modules.txt")
        shutil.copyfile(MODULES_TXT, self.modules)
        self.guide = os.path.join(self.tmp, "training.md")
        shutil.copyfile(TRAINING_DOC, self.guide)
        self.settings = os.path.join(self.tmp, "settings.md")
        shutil.copyfile(SETTINGS_DOC, self.settings)

    def _compare(self):
        declared = declared_modules(self.modules)
        self.assertIn("Habitat", declared, "fixture modules.txt did not parse")
        return module_doc_mismatches(
            declared,
            documented_modules(self.guide, TRAINING_MODULE_ANCHOR),
            documented_module_count(self.guide),
        )

    def _append_module(self, name):
        # The shipped modules.txt ends without a newline, so append, do not concatenate.
        text = _read(self.modules)
        with open(self.modules, "w", encoding="utf-8") as fh:
            fh.write(text.rstrip("\n") + "\n" + name + "\n")

    def _edit_guide(self, old, new):
        text = _read(self.guide)
        edited = text.replace(old, new, 1)
        self.assertNotEqual(edited, text, f"guide copy no longer contains {old!r}")
        with open(self.guide, "w", encoding="utf-8") as fh:
            fh.write(edited)

    def _compare_settings(self):
        declared = declared_modules(self.modules)
        self.assertIn("Habitat", declared, "fixture modules.txt did not parse")
        documented = documented_settings_modules(self.settings)
        self.assertTrue(documented, "fixture settings.md sentence did not parse")
        return module_doc_mismatches(
            declared, documented, documented_module_count(self.settings)
        )

    def _edit_settings(self, old, new):
        text = _read(self.settings)
        edited = text.replace(old, new, 1)
        self.assertNotEqual(edited, text, f"settings copy no longer contains {old!r}")
        with open(self.settings, "w", encoding="utf-8") as fh:
            fh.write(edited)

    def test_the_unmodified_copy_agrees(self):
        self.assertEqual(self._compare(), [], "baseline fixture must start clean")

    def test_a_module_added_to_modules_txt_reds_the_stale_guide(self):
        """The A-195 shape in reverse: the register moved, the published page did not."""
        self._append_module("Depot")
        mismatches = self._compare()
        self.assertEqual(len(mismatches), 2, f"added module went unreported: {mismatches}")
        self.assertTrue(any("'Depot'" in line and "no bullet" in line for line in mismatches))
        self.assertTrue(any("declares 4 names; it declares 5" in line for line in mismatches))

    def test_a_module_dropped_from_modules_txt_reds_the_stale_guide(self):
        """The exact A-195 defect: a bullet for a module the register no longer declares."""
        kept = [name for name in declared_modules(self.modules) if name != "Logistay"]
        with open(self.modules, "w", encoding="utf-8") as fh:
            fh.write("\n".join(kept) + "\n")

        mismatches = self._compare()
        self.assertEqual(len(mismatches), 2, f"dropped module went unreported: {mismatches}")
        self.assertTrue(any("'Logistay'" in line and "does not declare" in line for line in mismatches))
        self.assertTrue(any("declares 4 names; it declares 3" in line for line in mismatches))

    def test_a_module_added_correctly_on_both_sides_stays_green(self):
        """The lookalike: register and page changed together must not fail."""
        self._append_module("Depot")
        self._edit_guide("declares **four** names", "declares **five** names")
        self._edit_guide(
            "- **Apex Core** —", "- **Depot** — planted fixture module.\n- **Apex Core** —"
        )
        self.assertEqual(self._compare(), [], "a correctly documented module must stay green")

    def test_the_unmodified_settings_copy_agrees(self):
        self.assertEqual(self._compare_settings(), [], "baseline fixture must start clean")

    def test_a_module_added_to_modules_txt_reds_the_stale_settings_page(self):
        """Direction one: the register grew and the desk-page note did not."""
        self._append_module("Depot")
        mismatches = self._compare_settings()
        self.assertEqual(len(mismatches), 2, f"added module went unreported: {mismatches}")
        self.assertTrue(any("'Depot'" in line and "no bullet" in line for line in mismatches))
        self.assertTrue(any("declares 4 names; it declares 5" in line for line in mismatches))

    def test_a_module_dropped_from_modules_txt_reds_the_stale_settings_page(self):
        """Direction two — the exact A-208 defect: the note names a module the
        register no longer declares, which is what `SIM Operations` had become."""
        kept = [name for name in declared_modules(self.modules) if name != "Logistay"]
        with open(self.modules, "w", encoding="utf-8") as fh:
            fh.write("\n".join(kept) + "\n")

        mismatches = self._compare_settings()
        self.assertEqual(len(mismatches), 2, f"dropped module went unreported: {mismatches}")
        self.assertTrue(
            any("'Logistay'" in line and "does not declare" in line for line in mismatches)
        )
        self.assertTrue(any("declares 4 names; it declares 3" in line for line in mismatches))

    def test_a_module_added_correctly_to_both_sides_of_settings_stays_green(self):
        """The lookalike: register and note changed together must not fail."""
        self._append_module("Depot")
        self._edit_settings("declares **four** names", "declares **five** names")
        self._edit_settings("and **Logistay**.", "**Logistay**, and **Depot**.")
        self.assertEqual(
            self._compare_settings(), [], "a correctly documented module must stay green"
        )

    def test_appending_to_the_registry_never_concatenates(self):
        """The shipped modules.txt ends WITHOUT a trailing newline, and that is the
        framework's own doing: Module Def.on_update -> add_to_modules_txt and
        on_trash -> delete_module_from_file both write `"\\n".join(modules)`, and
        bench's app boilerplate writes the first line the same way. A naive append
        therefore yields a concatenated name — `LogistayDepot` was observed.

        Adding the trailing newline would be undone by the next Module Def insert,
        so the appender normalises instead. This proves it holds for a file that
        ends either way, which is exactly what makes the framework's rewrites a
        non-issue.
        """
        for trailing in ("", "\n"):
            with self.subTest(trailing=repr(trailing)):
                with open(self.modules, "w", encoding="utf-8") as fh:
                    fh.write("\n".join(declared_modules(MODULES_TXT)) + trailing)
                self._append_module("Depot")
                declared = declared_modules(self.modules)
                self.assertEqual(
                    declared[-2:], ["Logistay", "Depot"], f"append concatenated: {declared}"
                )
                self.assertNotIn("LogistayDepot", declared)


if __name__ == "__main__":
    unittest.main()
