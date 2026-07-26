# Copyright (c) 2026, AFMCO and contributors
"""Guard (A-175): the supervisor map's tile source stays overridable per deployment.

The default tile source is a RECORDED, ACCEPTED third-party fetch — the full decision,
including exactly what a tile request discloses, is the module docstring of
``www/masar_supervisor.py``. The acceptance is only defensible while a deployment that
needs a contracted or self-hosted source can switch to it WITHOUT a code change, so the
override path is the thing that has to be guarded, not the default.

That path has three links, and a break in any one is silent — the page keeps working,
it just keeps calling the third party:

  1. ``map_tile_override`` reads ``apex_map_tile_url`` from site_config and refuses a
     value that is neither https:// nor root-relative. Refusing is deliberate: an http://
     tile URL on an https page is blocked as mixed content, so a typo would take the map
     background out with no error anywhere, and a ``javascript:``-style value has no
     business reaching a URL the page hands to Leaflet.
  2. ``masar-supervisor.html`` projects the result as ``window.apex_map_tiles``.
  3. The built bundle reads that global. Asserted against the COMMITTED bundle, so a
     source-only edit that was never rebuilt cannot pass — that is the failure mode the
     Portal Bundles job exists for, and this catches it for this one wiring locally.

Standalone stub (A-205)
-----------------------
``masar_supervisor`` imports frappe at module scope, so running the command below
needs a fallback: the block after the imports stands up the minimum surface its
import chain touches (``frappe.sessions.get_csrf_token``, ``frappe.utils.cint``,
and — via ``portal_bootstrap`` -> ``driver_portal_theme`` — ``frappe._`` and
``frappe.model.document.Document``). Same idiom as
``apex_core/utils/test_guarded_index_dedupe.py``; under bench the REAL frappe is
already in ``sys.modules`` and the branch never runs.

Stubbing is the honest fix HERE, rather than deleting the claim, because the unit
under test needs none of it: ``map_tile_override`` is pure string validation over a
plain dict, and the other three tests read committed files. No test below CALLS the
stub, so it cannot fake a passing assertion — it only lets the module carrying the
function load. If ``masar_supervisor`` grows an import the stub does not cover, the
A-192 probe in ``tests/test_unit_test_coverage_guard.py`` reds and names this module.

Run standalone:  python3 -m unittest apex.www.test_masar_supervisor_map_tiles -v
"""

import sys
import types
import unittest
from pathlib import Path

# [#a205mt] Load-bearing only off-bench — see "Standalone stub" in the module docstring
# for what each entry is for and why stubbing cannot fake a pass here.
if "frappe" not in sys.modules:
    _fake_frappe = types.ModuleType("frappe")
    _fake_frappe._ = lambda msg, *a, **k: msg

    _fake_sessions = types.ModuleType("frappe.sessions")
    _fake_sessions.get_csrf_token = lambda *a, **k: ""

    _fake_utils = types.ModuleType("frappe.utils")
    _fake_utils.cint = lambda value, *a, **k: int(value or 0)

    _fake_model = types.ModuleType("frappe.model")
    _fake_document = types.ModuleType("frappe.model.document")
    _fake_document.Document = type("Document", (), {})
    _fake_model.document = _fake_document

    _fake_frappe.sessions = _fake_sessions
    _fake_frappe.utils = _fake_utils
    _fake_frappe.model = _fake_model

    sys.modules["frappe"] = _fake_frappe
    sys.modules["frappe.sessions"] = _fake_sessions
    sys.modules["frappe.utils"] = _fake_utils
    sys.modules["frappe.model"] = _fake_model
    sys.modules["frappe.model.document"] = _fake_document

from apex.www.masar_supervisor import map_tile_override  # noqa: E402

WWW = Path(__file__).resolve().parent
BUNDLE = WWW.parent / "public" / "route_supervisor_portal" / "assets" / "index.js"


class TestMapTileOverride(unittest.TestCase):
    def test_unset_config_keeps_the_components_own_default(self):
        # Empty, not the OSM literal: the default lives in ONE place (the component),
        # so the two can never drift into disagreeing about the accepted source.
        self.assertEqual(map_tile_override({}), {"url": "", "attribution": ""})

    def test_an_https_source_is_accepted_with_its_attribution(self):
        conf = {
            "apex_map_tile_url": "https://tiles.example.sa/{z}/{x}/{y}.png",
            "apex_map_tile_attribution": "Contracted tiles",
        }
        self.assertEqual(
            map_tile_override(conf),
            {"url": "https://tiles.example.sa/{z}/{x}/{y}.png", "attribution": "Contracted tiles"},
        )

    def test_a_self_hosted_root_relative_source_is_accepted(self):
        # The self-hosting escape hatch: tiles served by this very site.
        self.assertEqual(map_tile_override({"apex_map_tile_url": "/tiles/{z}/{x}/{y}.png"})["url"],
                         "/tiles/{z}/{x}/{y}.png")

    def test_a_scheme_that_would_break_or_inject_is_ignored(self):
        for bad in ("http://tiles.example.sa/{z}/{x}/{y}.png", "javascript:alert(1)", "  ", "//x/y"):
            with self.subTest(bad=bad):
                self.assertEqual(map_tile_override({"apex_map_tile_url": bad})["url"], "")

    def test_the_shell_projects_the_override_to_the_page(self):
        shell = (WWW / "masar-supervisor.html").read_text(encoding="utf-8")
        self.assertIn("window.apex_map_tiles", shell)
        self.assertIn("map_tiles | tojson", shell, "the value must be JSON-escaped into the script")

    def test_the_committed_bundle_actually_reads_the_override(self):
        self.assertTrue(BUNDLE.is_file(), f"{BUNDLE} is missing")
        self.assertIn(
            "apex_map_tiles",
            BUNDLE.read_text(encoding="utf-8"),
            "the committed route_supervisor bundle predates the override — rebuild it "
            "(npm ci && npm run build -w route_supervisor) and commit the result, or "
            "every deployment silently keeps calling the default tile host",
        )


if __name__ == "__main__":
    unittest.main()
