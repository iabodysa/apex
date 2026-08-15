# Copyright (c) 2026, afmcoltd
"""Structural guard: every report-scope call site names the DocType it reads.

``report_project_scope`` / ``report_building_scope`` / ``report_company_scope`` all take
``doctype=None``. That default is not a convenience — it is the ``applicable_for``
narrowing key. Frappe passes the DocType on the LIST path
(``frappe/model/db_query.py`` calls each ``permission_query_conditions`` hook as
``frappe.call(method, user, doctype=self.doctype)``), which is what lets an admin write a
User Permission that applies to ONE DocType. A report or dashboard endpoint that omits
``doctype`` re-opens every tenant the admin narrowed away, on that surface only, and
nothing about the code reads as wrong.

So the invariant is checked in the SOURCE, by AST, rather than by grep: a text search
matches a docstring, misses a call split across lines, and cannot tell a keyword argument
from a substring. Two things are asserted — that every call site passes ``doctype``, and
that every value passed is a DocType that actually exists, because a DocType name that
does not exist matches nothing and silently narrows the scope to empty.

Test modules are out of scope: they stub and drive these wrappers deliberately, and a
stub that omits ``doctype`` leaks nothing.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

import frappe
from frappe.tests.utils import FrappeTestCase

import apex

# The directory holding the INSTALLED apex/ package, so the walk below reads the sources
# that actually run rather than a checkout that may not be the one on the bench.
ROOT = Path(apex.__file__).resolve().parents[1]
APEX = ROOT / "apex"

WRAPPERS = frozenset(
    {"report_project_scope", "report_building_scope", "report_company_scope"}
)

# Call sites deliberately left without a ``doctype``, keyed by (relative path, enclosing
# function) so the entry survives an unrelated edit above it but dies with the function.
# An entry that no longer matches a real site fails the test, so an exemption cannot
# outlive the reason for it.
UNDECIDED = {
    (
        "habitat/api/arrivals_desk.py",
        "search_arrivals_workers",
    ): (
        "One scope value is applied to BOTH `Housing Assignment`.building (the housed "
        "parties) and `Temporary Worker`.building (the search results), and the two "
        "reads are unioned into one list. Naming either DocType would drop a User "
        "Permission narrowed to the other and hide rows the desk must see, so the axis "
        "is left for the owner to name."
    ),
}


def _callee(func):
    """Return the called NAME for an attribute or bare call, else None."""
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return None


def _sites(tree):
    """Yield ``(function, lineno, call)`` for every wrapper call in a parsed module."""
    found = []

    def walk(node, function):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                walk(child, child.name)
                continue
            if isinstance(child, ast.Call) and _callee(child.func) in WRAPPERS:
                found.append((function, child.lineno, child))
            walk(child, function)

    walk(tree, "<module>")
    return found


def _collect():
    """Return ``(passing, missing)`` call sites across the shipped app sources.

    ``passing`` is ``[(rel, function, lineno, doctype_or_None)]`` — the value is None when
    ``doctype`` is passed as something other than a literal string, which the DocType
    existence check below cannot read and therefore skips.
    """
    passing, missing = [], []
    for path in sorted(APEX.rglob("*.py")):
        if path.name.startswith("test_"):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        rel = path.relative_to(APEX).as_posix()
        for function, lineno, call in _sites(tree):
            keyword = next((k for k in call.keywords if k.arg == "doctype"), None)
            if keyword is None:
                missing.append((rel, function, lineno))
                continue
            value = keyword.value
            literal = value.value if isinstance(value, ast.Constant) else None
            passing.append((rel, function, lineno, literal))
    return passing, missing


class TestReportScopeCallSitesPassDoctype(FrappeTestCase):
    def test_every_call_site_passes_a_doctype(self):
        """Every shipped call site names its DocType, or is a declared exemption."""
        _, missing = _collect()
        undeclared = [s for s in missing if (s[0], s[1]) not in UNDECIDED]
        self.assertEqual(
            undeclared,
            [],
            "report_*_scope called without doctype= — the applicable_for narrowing is "
            "skipped and every User Permission scoped to another DocType widens here:\n"
            + "\n".join(f"  apex/{rel}:{line} in {fn}()" for rel, fn, line in undeclared),
        )

    def test_no_exemption_outlives_its_call_site(self):
        """A declared exemption must still match a real doctype-less call site."""
        _, missing = _collect()
        live = {(rel, fn) for rel, fn, _ in missing}
        stale = sorted(set(UNDECIDED) - live)
        self.assertEqual(
            stale, [], f"UNDECIDED entries no longer match a call site: {stale}"
        )

    def test_every_passed_doctype_exists(self):
        """A DocType name that does not exist matches nothing and empties the scope."""
        passing, _ = _collect()
        unknown = sorted(
            {
                (rel, line, name)
                for rel, _fn, line, name in passing
                if name and not frappe.db.exists("DocType", name)
            }
        )
        self.assertEqual(
            unknown, [], f"doctype= names no installed DocType: {unknown}"
        )


if __name__ == "__main__":
    unittest.main()
