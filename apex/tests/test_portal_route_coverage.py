# Copyright (c) 2026, AFMCO and contributors
"""Served portal routes and the bundle-guard matrix must agree.

Two independent lists describe the same set of portal SPAs and had drifted apart:

  1. SERVED   — ``apex/www/<route>.html``, each shell mounting one built bundle.
  2. GUARDED  — the ``bundle-guard`` matrix in .github/workflows/portal-bundles.yml,
                which rebuilds each bundle and fails on stale committed output.

A route served but absent from (2) ships a bundle nothing proves is fresh. The
counts legitimately differ — ``worker_portal`` is served at BOTH /driver and
/masar — so this guard compares the mapped SETS, never the raw counts.

There was a third list: SMOKED, the ``_PORTALS`` route list of a browser harness
that opened each portal and asserted the SPA actually mounts. That harness is the
maintainer's tooling and is not published with the app, so the checks that read it
moved out with it. Nothing here proves a portal still MOUNTS — only that every
served bundle is rebuilt and every rebuilt bundle is served.

Both lists are parsed STRUCTURALLY — the shells through an HTML parser, the workflow
through a YAML parser — so a safe refactor (reordering, relabelling, reformatting)
does not red this guard; only a real coverage change does.
"""

import re
import unittest
from html.parser import HTMLParser
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = APP_ROOT.parent
WWW = APP_ROOT / "www"
BUNDLES_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "portal-bundles.yml"

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
    """Bundle names the portal-bundles `bundle-guard` matrix rebuilds.

    yaml is imported HERE, not at module scope: it is the only dependency in this file
    and only this half needs it, so the served-route parser above stays importable
    wherever PyYAML is not installed.
    """
    import yaml

    workflow = yaml.safe_load(BUNDLES_WORKFLOW.read_text(encoding="utf-8"))
    legs = workflow["jobs"]["bundle-guard"]["strategy"]["matrix"]["include"]
    return {leg["portal"] for leg in legs if leg.get("portal")}


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
    BUNDLES_WORKFLOW.exists(),
    "the workflow sources are not present in this install",
)
class TestPortalCoverageSetsAgree(unittest.TestCase):
    def test_parsers_find_the_guard_set(self):
        self.assertTrue(guarded_bundles(), "bundle-guard matrix parse returned nothing")

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


if __name__ == "__main__":
    unittest.main()
