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
sidebar, and the exact list of roles it grants. Nothing in the tree referenced
the page, so a role added to a workspace JSON left the
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

Two further anchors on that page are part of the same contract, because the row
comparison alone is correct without being COMPLETE:

- The sentence stating routing is pure `www/` convention with no route-rule or
  page-renderer indirection. It is the PREMISE that makes reading `www/` a whole
  account of the served routes; hooks.py is checked against it, so declaring a
  route rule fails rather than quietly giving the table a route to miss.
- Each portal row's API module and endpoint count, written `(N endpoints)` in
  the row and `serves N` in the prose beneath. The count is derived by counting
  module-level `@frappe.whitelist` functions, and the page states each one twice,
  so the two halves disagreeing fails on its own.

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
HOOKS_PY = os.path.join(APP_ROOT, "hooks.py")

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

# A portal's server-side API surface, stated as a backticked dotted module path
# followed by its endpoint count. Two published shapes, one claim: "(N endpoints)"
# inside a route row's gate cell, and "serves N" in the prose under the table.
ENDPOINT_CLAIM = re.compile(
    r"`(?P<module>" + APP_PKG + r"(?:\.[a-z0-9_]+)+)`\s*"
    r"(?:\((?P<parenthesised>\d+) endpoints?\)|serves (?P<inline>\d+))"
)

# The sentence the whole route derivation rests on. Reading apex/www/ is a
# COMPLETE account of the served routes only while it holds; a route rule in
# hooks.py would serve a route no shell backs, and the scan would never see it.
WWW_ONLY_CLAIM = (
    "routing is pure `www/` file convention, with no `website_route_rules` "
    "or `page_renderer` indirection"
)
ROUTING_INDIRECTION_HOOKS = ("website_route_rules", "page_renderer")

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


def _replace_once(case, path, old, new):
    """Rewrite a MIRRORED document, asserting the pattern was there to replace.

    Every falsifiability class below plants its drift this way, so it is one
    helper: a plant whose pattern silently matched nothing would leave the
    fixture unmodified and "prove" the guard green against an untouched file.
    """
    text = _read(path)
    edited = text.replace(old, new, 1)
    case.assertNotEqual(
        edited, text, f"{os.path.basename(path)} no longer contains {old!r}"
    )
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(edited)


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


def documented_endpoint_counts(path=README):
    """{dotted module: {claimed counts}} for every endpoint claim in the README.

    A set, not an int, on purpose: the README states each portal's endpoint count
    TWICE — once in the route row's gate cell and once in the prose beneath — so
    the two halves disagreeing is itself a defect this reports.
    """
    counts = {}
    for match in ENDPOINT_CLAIM.finditer(_flat(_read(path))):
        claimed = match.group("parenthesised") or match.group("inline")
        counts.setdefault(match.group("module"), set()).add(int(claimed))
    return counts


def shipped_endpoint_count(module, repo_root=REPO_ROOT):
    """How many module-level `@frappe.whitelist` functions `module` ships, or None.

    Module level only: a whitelist nested inside another function is not a
    reachable endpoint, so counting it would inflate the published number.
    """
    path = os.path.join(repo_root, *module.split(".")) + ".py"
    if not os.path.isfile(path):
        return None
    total = 0
    for node in ast.parse(_read(path)).body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            target = decorator.func if isinstance(decorator, ast.Call) else decorator
            if getattr(target, "attr", None) == "whitelist":
                total += 1
                break
    return total


def endpoint_count_mismatches(documented, repo_root=REPO_ROOT):
    """Every published endpoint count that is not the count the module ships."""
    report = []
    for module in sorted(documented):
        claimed = documented[module]
        shipped = shipped_endpoint_count(module, repo_root)
        if shipped is None:
            report.append(f"{module}: the README names it but no such module ships")
        elif len(claimed) > 1:
            report.append(
                f"{module}: the README claims {sorted(claimed)} in different places; "
                "the route row and the prose beneath it must state one number"
            )
        elif claimed != {shipped}:
            report.append(
                f"{module}: the README says {sorted(claimed)[0]} endpoints but the "
                f"module whitelists {shipped}"
            )
    return report


def hooks_routing_indirection(path=HOOKS_PY):
    """The route-indirection hooks `hooks.py` assigns at module level, if any."""
    declared = set()
    for node in ast.parse(_read(path)).body:
        targets = node.targets if isinstance(node, ast.Assign) else []
        if isinstance(node, ast.AnnAssign):
            targets = [node.target]
        for target in targets:
            if isinstance(target, ast.Name) and target.id in ROUTING_INDIRECTION_HOOKS:
                declared.add(target.id)
    return sorted(declared)


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

    def test_the_readme_still_states_the_www_only_routing_claim(self):
        """The anchor that makes the scan above COMPLETE, not merely correct.

        Reading apex/www/ accounts for every served route only while the README's
        no-indirection sentence is true. Delete or reword the sentence and the
        derivation loses its stated premise, so the sentence is part of the
        contract and is checked as one.
        """
        self.assertIn(
            WWW_ONLY_CLAIM,
            _flat(_read(README)),
            "the README no longer states that routing is pure www/ file convention. "
            "That sentence is the premise of the route table's derivation — restore "
            f"it verbatim, or teach this guard the new routing source: {WWW_ONLY_CLAIM!r}",
        )

    def test_hooks_declares_no_routing_indirection(self):
        """And the claim must be TRUE, or the table can omit a served route."""
        declared = hooks_routing_indirection()
        self.assertEqual(
            declared,
            [],
            "hooks.py now declares route indirection, so apex/www/ is no longer the "
            "whole routing story and the README's served-routes table can silently "
            f"omit a route: {declared}",
        )

    def test_the_published_endpoint_counts_are_the_shipped_counts(self):
        """Each portal row names its API module and how many endpoints it serves."""
        documented = documented_endpoint_counts()
        self.assertGreaterEqual(
            len(documented), 2, "no endpoint claim parsed — the README pattern broke"
        )
        mismatches = endpoint_count_mismatches(documented)
        self.assertEqual(
            mismatches,
            [],
            "README.md misstates a portal's endpoint count. A claim reads as a "
            "backticked dotted module path followed by `(N endpoints)` in the route "
            f"row, or `serves N` in the prose beneath it: {mismatches}",
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


if __name__ == "__main__":
    unittest.main()
