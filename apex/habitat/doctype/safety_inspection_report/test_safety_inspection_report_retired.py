# Copyright (c) 2026, AFMCO and contributors
"""Nothing shipped may CREATE a Safety Inspection Report, or offer one to create.

Removing the workspace link and marking the DocType ``read_only`` closes neither
route: root ``read_only`` is labelled "User Cannot Search", and
frappe/utils/user.py:130-144 diverts ``can_read`` only for a read-WITHOUT-create
grant, so every role holding create keeps it. A whitelisted POST can still insert
AND submit one on every click while both of those look applied.

Deprecation is a claim about REACHABILITY, so the guard is about reachability:

  * no production module builds the record (AST, not grep — a creation site is a
    dict literal or a ``new_doc`` argument, not any mention of the name);
  * the Safety Map desk page calls no retired endpoint;
  * no shipped DocType offers it as a form-dashboard connection.

It says nothing about the DATA. Every historical report, and every back-link
column pointing at one, stays exactly where it is; ``source_inspection`` on
Maintenance Request and ``linked_inspection`` on Safety Task Execution are kept
deliberately and only made read-only, so this guard must NOT be widened into "the
name may not appear".

Frappe-free by construction — it reads the shipped tree, so it runs without a site:

    python3 -m unittest apex.habitat.api.test_safety_inspection_report_retired
"""

from __future__ import annotations

import ast
import glob
import json
import os
import unittest

from apex.tests.source_tree import APP_ROOT, parse, production_py_files, rel

DEPRECATED = "Safety Inspection Report"
REPLACEMENT = "Safety Round"

# The module that owned the retired writer, and the desk page that called it.
SAFETY_MAP_PY = os.path.join(APP_ROOT, "habitat", "api", "safety_map.py")
SAFETY_MAP_JS = os.path.join(APP_ROOT, "habitat", "page", "safety_map", "safety_map.js")
RETIRED_ENDPOINT = "log_building_inspection"

# Its own JSON names itself in ``amended_from`` and in its links; amending an
# existing submitted report is native and is not a new record.
SELF = os.path.join("habitat", "doctype", "safety_inspection_report")


def _creates(tree):
    """DocType names this module constructs: ``{"doctype": X}`` dict literals and
    ``new_doc(X)`` / ``get_doc(X, ...)`` leading arguments.

    A creation SITE, not a mention. finding_fanout names the doctype in a
    comparison (``source_doc.doctype == _SIR_DOCTYPE``) to decide which back-link
    to stamp, and building_operations_summary names it in a ``get_all`` filter to
    count history — both are legitimate and neither builds anything.
    """
    built = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if isinstance(key, ast.Constant) and key.value == "doctype":
                    if isinstance(value, ast.Constant) and isinstance(value.value, str):
                        built.add(value.value)
        elif isinstance(node, ast.Call):
            name = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
            if name in ("new_doc", "get_doc") and node.args:
                first = node.args[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    built.add(first.value)
    return built


def _shipped_doctype_schemas():
    """``(path, schema)`` for every DocType JSON apex ships."""
    found = []
    pattern = os.path.join(APP_ROOT, "**", "doctype", "*", "*.json")
    for path in sorted(glob.glob(pattern, recursive=True)):
        with open(path, encoding="utf-8") as handle:
            try:
                schema = json.load(handle)
            except ValueError:
                continue
        if isinstance(schema, dict) and "fields" in schema and "module" in schema:
            found.append((path, schema))
    return found


class TestNoProductionCodeCreatesTheReport(unittest.TestCase):
    def setUp(self):
        self.modules = production_py_files()

    def test_the_scan_is_non_vacuous(self):
        """"Nothing found" is what a broken scan reports too, so the absence only
        means something once the scan is shown to see a real creation site."""
        self.assertGreater(len(self.modules), 100, "the production-module scan is empty")
        tree = parse(os.path.join(APP_ROOT, "habitat", "api", "safety_checklist.py"))
        self.assertIsNotNone(tree, "safety_checklist.py did not parse")
        self.assertIn(
            REPLACEMENT,
            _creates(tree),
            "the AST scan cannot see safety_checklist building a Safety Round, so it "
            "would not see a Safety Inspection Report being built either",
        )

    def test_no_production_module_builds_the_deprecated_report(self):
        offenders = []
        for path in self.modules:
            tree = parse(path)
            if tree is not None and DEPRECATED in _creates(tree):
                offenders.append(rel(path))
        self.assertEqual(
            offenders,
            [],
            "{0} is deprecated in favour of {1} and nothing may produce a new one. "
            "Record the finding on a {1} + its Safety Task Execution rows, which "
            "carry the maker-checker gate. Offenders: {2}".format(
                DEPRECATED, REPLACEMENT, offenders
            ),
        )


class TestSafetyMapWritesNothing(unittest.TestCase):
    """The surface that kept the record alive: a whitelisted POST that inserted
    AND submitted one report per click, from the same session that authored it."""

    def test_the_retired_endpoint_is_gone(self):
        tree = parse(SAFETY_MAP_PY)
        self.assertIsNotNone(tree, "safety_map.py did not parse")
        names = {
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        self.assertIn("get_safety_map", names, "the reader is gone too — wrong file?")
        self.assertNotIn(
            RETIRED_ENDPOINT,
            names,
            "safety_map.{0} built and submitted a {1}; it is retired and the page "
            "routes its tiles to {2} instead".format(RETIRED_ENDPOINT, DEPRECATED, REPLACEMENT),
        )

    def test_the_desk_page_calls_no_retired_endpoint(self):
        with open(SAFETY_MAP_JS, encoding="utf-8") as handle:
            source = handle.read()
        self.assertIn(
            "apex.habitat.api.safety_map.get_safety_map",
            source,
            "the page calls no safety_map endpoint at all — the scan is reading the "
            "wrong file",
        )
        self.assertNotIn(
            RETIRED_ENDPOINT,
            source,
            "the Safety Map page still calls the retired inspection writer",
        )


class TestNoFormDashboardOffersTheReport(unittest.TestCase):
    """A DocType ``links`` row is a live entry point, not decoration: Frappe renders
    the connection with a create affordance for any role holding create, which is
    every role on this record. Building offered one, and Maintenance Request offered
    a second through the report's child table."""

    def setUp(self):
        self.schemas = _shipped_doctype_schemas()

    def test_the_scan_is_non_vacuous(self):
        self.assertGreater(len(self.schemas), 100, "the DocType JSON scan is empty")
        by_name = {schema.get("name"): schema for _p, schema in self.schemas}
        self.assertIn("Building", by_name, "the scan does not see Building")
        targets = {row.get("link_doctype") for row in by_name["Building"].get("links") or []}
        self.assertIn(
            REPLACEMENT,
            targets,
            "Building no longer offers the replacement connection the deprecated one "
            "was swapped for — the scan is not reading links rows",
        )

    def test_no_doctype_links_to_the_deprecated_report(self):
        offenders = []
        for path, schema in self.schemas:
            if SELF in path:
                continue
            for row in schema.get("links") or []:
                if DEPRECATED in (row.get("link_doctype"), row.get("parent_doctype")):
                    offenders.append("{0} -> {1}".format(rel(path), row))
        self.assertEqual(
            offenders,
            [],
            "a form-dashboard connection to {0} is an entry point that offers the "
            "deprecated record for creation; connect {1} instead: {2}".format(
                DEPRECATED, REPLACEMENT, offenders
            ),
        )


if __name__ == "__main__":
    unittest.main()
