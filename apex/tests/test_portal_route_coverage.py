# Copyright (c) 2026, AFMCO and contributors
"""Served portal routes, the bundle-guard matrix and the e2e smoke list must agree.

Three independent lists describe the same set of portal SPAs and had drifted apart:

  1. SERVED   — ``apex/www/<route>.html``, each shell mounting one built bundle.
  2. GUARDED  — the ``bundle-guard`` matrix in .github/workflows/portal-bundles.yml,
                which rebuilds each bundle and fails on stale committed output.
  3. SMOKED   — ``_PORTALS`` in e2e/portal_smoke_spec.py, the runtime mount smoke.

A route served but absent from (2) ships a bundle nothing proves is fresh; absent
from (3) it ships a bundle nothing proves still mounts. The counts legitimately
differ — ``worker_portal`` is served at BOTH /driver and /masar — so this guard
compares the mapped SETS, never the raw counts.

A route may be held out of the smoke list, but only with the reason written INSIDE
the ``_PORTALS`` literal, next to where its entry would sit. That keeps a temporary
exclusion self-documenting instead of silently shrinking coverage.

Every list is parsed STRUCTURALLY — the shells through an HTML parser, the workflow
through a YAML parser, the route list through ``ast`` — so a safe refactor
(reordering, relabelling, reformatting) does not red this guard; only a real
coverage change does.
"""

import ast
import re
import tokenize
import unittest
from html.parser import HTMLParser
from pathlib import Path

import yaml

APP_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = APP_ROOT.parent
WWW = APP_ROOT / "www"
BUNDLES_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "portal-bundles.yml"
SMOKE_SPEC = REPO_ROOT / "e2e" / "portal_smoke_spec.py"

# A shell loads its SPA as /assets/apex/<bundle>/assets/index.js.
BUNDLE_SRC = re.compile(r"^/assets/apex/([A-Za-z0-9_]+)/assets/index\.js(?:\?.*)?$")

# The app has served at least this many portal shells since the split; a lower
# count means the shell parser broke, not that portals were retired.
MIN_SERVED_SHELLS = 5


class _ShellParser(HTMLParser):
    """Collect the SPA mount node and the bundle(s) one www shell loads."""

    def __init__(self):
        super().__init__()
        self.has_mount = False
        self.bundles = set()

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "div" and attributes.get("id") == "app":
            self.has_mount = True
        if tag == "script":
            match = BUNDLE_SRC.match(attributes.get("src") or "")
            if match:
                self.bundles.add(match.group(1))


def served_routes() -> dict[str, set[str]]:
    """Map every served portal route to the bundle(s) its shell mounts.

    A www page counts as a portal only when it has BOTH the ``#app`` mount node and
    a portal bundle script, so redirect-only routes (e.g. /housing-count) and any
    plain server-rendered page are excluded without needing a hand-kept list.
    """
    routes: dict[str, set[str]] = {}
    for shell in sorted(WWW.glob("*.html")):
        parser = _ShellParser()
        parser.feed(shell.read_text(encoding="utf-8"))
        if parser.has_mount and parser.bundles:
            routes[shell.stem] = parser.bundles
    return routes


def guarded_bundles() -> set[str]:
    """Bundle names the portal-bundles `bundle-guard` matrix rebuilds."""
    workflow = yaml.safe_load(BUNDLES_WORKFLOW.read_text(encoding="utf-8"))
    legs = workflow["jobs"]["bundle-guard"]["strategy"]["matrix"]["include"]
    return {leg["portal"] for leg in legs if leg.get("portal")}


def _smoke_assignment():
    """The module-level ``_PORTALS`` Assign node of the smoke spec."""
    tree = ast.parse(SMOKE_SPEC.read_text(encoding="utf-8"))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if any(isinstance(t, ast.Name) and t.id == "_PORTALS" for t in node.targets):
            return node
    return None


def smoke_entries() -> list[tuple[str, str]]:
    """The (route, label) pairs the e2e smoke spec opens."""
    node = _smoke_assignment()
    if node is None:
        return []
    return [tuple(entry) for entry in ast.literal_eval(node.value)]


def smoke_exclusion_notes() -> str:
    """Comment text written INSIDE the ``_PORTALS`` literal.

    Read with ``tokenize`` rather than matched against source text, so the guard
    checks that a held-out route is explained without dictating any wording.
    """
    node = _smoke_assignment()
    if node is None:
        return ""
    notes = []
    with SMOKE_SPEC.open("rb") as handle:
        for token in tokenize.tokenize(handle.readline):
            if token.type != tokenize.COMMENT:
                continue
            if node.lineno <= token.start[0] <= node.end_lineno:
                notes.append(token.string)
    return "\n".join(notes)


class TestServedRouteParsing(unittest.TestCase):
    """Sentinels — a broken parser must red here, not pass the set checks vacuously."""

    def test_shell_parser_finds_the_served_portals(self):
        routes = served_routes()
        self.assertGreaterEqual(
            len(routes),
            MIN_SERVED_SHELLS,
            f"www shell parser found only {sorted(routes)} — the parser broke or "
            "the shells moved; the coverage checks below would pass vacuously",
        )

    def test_every_served_shell_mounts_exactly_one_bundle(self):
        offenders = {r: sorted(b) for r, b in served_routes().items() if len(b) != 1}
        self.assertEqual(
            offenders,
            {},
            f"a portal shell must mount exactly one bundle: {offenders}",
        )


@unittest.skipUnless(
    BUNDLES_WORKFLOW.exists() and SMOKE_SPEC.exists(),
    "workflow/e2e sources are not present in this install",
)
class TestPortalCoverageSetsAgree(unittest.TestCase):
    def test_parsers_find_the_guard_and_smoke_sets(self):
        self.assertTrue(guarded_bundles(), "bundle-guard matrix parse returned nothing")
        self.assertTrue(smoke_entries(), "_PORTALS parse returned nothing")

    def test_every_served_bundle_is_rebuilt_by_the_bundle_guard(self):
        guarded = guarded_bundles()
        missing = {
            route: sorted(bundles - guarded)
            for route, bundles in served_routes().items()
            if bundles - guarded
        }
        self.assertEqual(
            missing,
            {},
            "served route(s) whose bundle no bundle-guard matrix leg rebuilds — a "
            f"stale committed bundle would ship unnoticed: {missing}",
        )

    def test_every_guarded_bundle_is_actually_served(self):
        served = set().union(*served_routes().values())
        orphans = sorted(guarded_bundles() - served)
        self.assertEqual(
            orphans,
            [],
            "bundle-guard matrix leg(s) for bundles no www shell serves — drop the "
            f"leg or add the shell: {orphans}",
        )

    def test_every_served_route_is_smoked_or_documented(self):
        smoked = {route for route, _ in smoke_entries()}
        notes = smoke_exclusion_notes()
        undocumented = [
            route
            for route in sorted(served_routes())
            if route not in smoked and route not in notes
        ]
        self.assertEqual(
            undocumented,
            [],
            "served route(s) neither smoked nor explained: add the route to "
            "_PORTALS in e2e/portal_smoke_spec.py, or write why it is held out in "
            f"a comment inside that list: {undocumented}",
        )

    def test_smoke_list_has_no_unserved_route(self):
        served = served_routes()
        strays = sorted({route for route, _ in smoke_entries()} - set(served))
        self.assertEqual(
            strays,
            [],
            "_PORTALS names route(s) no www shell serves — the smoke would open a "
            f"404: {strays}",
        )

    def test_each_smoked_route_appears_once_with_a_distinct_label(self):
        entries = smoke_entries()
        routes = [route for route, _ in entries]
        duplicates = sorted({r for r in routes if routes.count(r) > 1})
        self.assertEqual(duplicates, [], f"route listed twice in _PORTALS: {duplicates}")

        labels = [label for _, label in entries]
        blank = [route for route, label in entries if not str(label).strip()]
        self.assertEqual(blank, [], f"route(s) with an empty smoke label: {blank}")
        shared = sorted({lb for lb in labels if labels.count(lb) > 1})
        self.assertEqual(
            shared,
            [],
            "two routes share one smoke label, so a failure line cannot say which "
            f"portal broke: {shared}",
        )


if __name__ == "__main__":
    unittest.main()
