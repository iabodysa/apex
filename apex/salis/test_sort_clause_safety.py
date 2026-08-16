# Copyright (c) 2026, AFMCO and contributors
"""App-wide: an ``order_by``/``group_by`` literal may not call a SQL function frappe rejects.

frappe version-15 replaced ``validate_order_by_and_group_by``'s function BLACKLIST with an
ALLOWLIST (``ALLOWED_ORDER_BY_FUNCTIONS``, frappe/model/db_query.py). A sort clause calling
anything outside it raises ValidationError inside ``frappe.get_all`` — which a portal sees
as HTTP 417, on every call, regardless of dataset or user. A bench pinned to an older frappe
still carries the blacklist, so the same call succeeds locally and fails only against a
freshly cloned version-15: the difference is the FRAMEWORK, not the site.

The scan reads the allowlist off the installed frappe rather than restating it, so a
framework upgrade that widens or narrows the set is followed automatically. Order in Python
when a clause needs a function frappe will not take.
"""

import ast
import os
import re
from pathlib import Path

from frappe.tests.utils import FrappeTestCase

import apex

_APP_ROOT = str(Path(apex.__file__).resolve().parent)
_SORT_KWARGS = ("order_by", "group_by")
_FUNCTION_CALL = re.compile(r"\b(\w+)\s*\(")


def _allowed_sort_functions():
    """Frappe's own allowlist when the installed version exposes it, else NOTHING.

    Reading the constant instead of copying it keeps the guard in step with the
    framework; the empty fallback keeps it strict on a bench pinned to the older
    blacklist build, where an unsafe literal would otherwise pass unnoticed."""
    from frappe.model import db_query

    return set(getattr(db_query, "ALLOWED_ORDER_BY_FUNCTIONS", ()) or ())


def _sort_literals(tree):
    """(kwarg, literal) for every literal string passed as order_by/group_by."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for kw in node.keywords:
            if kw.arg in _SORT_KWARGS and isinstance(kw.value, ast.Constant):
                if isinstance(kw.value.value, str):
                    yield kw.arg, kw.value.value


def _app_python_files():
    for root, dirs, files in os.walk(_APP_ROOT):
        dirs[:] = [d for d in dirs if d not in {"__pycache__", "node_modules", "public"}]
        for f in files:
            if f.endswith(".py"):
                yield os.path.join(root, f)


class TestSortClauseSafety(FrappeTestCase):
    """App-wide: an order_by/group_by literal may not call a function frappe rejects."""

    def test_no_disallowed_sql_function_in_any_sort_clause(self):
        allowed = _allowed_sort_functions()
        offenders = []
        for path in _app_python_files():
            with open(path, encoding="utf-8") as fh:
                source = fh.read()
            try:
                tree = ast.parse(source)
            except SyntaxError:
                continue
            for kwarg, literal in _sort_literals(tree):
                for func in _FUNCTION_CALL.findall(literal.lower()):
                    if func not in allowed:
                        rel = os.path.relpath(path, _APP_ROOT)
                        offenders.append(f"  apex/{rel}: {kwarg}={literal!r} calls {func}()")

        self.assertEqual(
            sorted(offenders),
            [],
            "DatabaseQuery.validate_order_by_and_group_by allows only the functions in "
            "frappe's ALLOWED_ORDER_BY_FUNCTIONS; anything else raises ValidationError, "
            "which a portal sees as HTTP 417. Sort in Python instead:\n"
            + "\n".join(sorted(offenders)),
        )

    def test_guard_actually_detects_a_disallowed_function(self):
        """Guard-of-the-guard: the scan must both find real literals and reject a bad one."""
        found = list(_sort_literals(ast.parse('frappe.get_all("X", order_by="field(a,\'b\') desc")')))
        self.assertEqual(found, [("order_by", "field(a,'b') desc")])
        self.assertNotIn("field", _allowed_sort_functions())
        scanned = sum(1 for _ in _app_python_files())
        self.assertGreater(scanned, 100, "app scan returned implausibly few python files")
