# Copyright (c) 2026, afmcoltd
"""A portal-backend function with no reference outside its own test is not shipped.

Four such functions accumulated before anything looked for them, and each was kept alive only by
a test written for it — a shape that reads as coverage and is really a symbol nobody calls. The
last of them, `_live_dispatch_trip` in `salis/api/masar_routes.py`, sat unreferenced long enough
to be raised as a question and answered by deletion. This guard is what would have found all four
on the day they went dark.

WHAT IT DELIBERATELY DOES NOT LOOK AT, because a static reference count is structurally blind to
all three and a guard that flagged them would be silenced within a week:

- a `@frappe.whitelist()` endpoint, reachable as `/api/method/<dotted.path>` by any client,
  including one that composes the path at run time the way `logistay/api/telecom_control.py` does;
- anything under `www/`, whose functions are named from a Jinja template rather than from Python —
  `portal_sections` is reached as `context.portal_sections`;
- a name that appears anywhere outside a test file, however it is spelled.

What is left is the shape this exists for: a PLAIN module-level function, not whitelisted, not a
template context, whose only surviving reference is the test written for it.
"""

from __future__ import annotations

import ast
import os
import re
import unittest

import frappe

_APP = frappe.get_app_path("apex")
_REPO = os.path.dirname(_APP)

PORTAL_TREES = (
    "salis/api",
    "salis/tasks",
    "habitat/api",
    "habitat/tasks",
    "logistay/api",
    "logistay/tasks",
)

SEARCHED_SUFFIXES = (".py", ".js", ".json", ".html", ".vue", ".txt", ".md")
SKIP_DIRS = {"__pycache__", "node_modules", ".git", "dist", "public"}


def _is_test(path: str) -> bool:
    base = os.path.basename(path)
    return base.startswith("test_") or f"{os.sep}tests{os.sep}" in path


def _is_whitelisted(node: ast.FunctionDef) -> bool:
    """True when the function is reachable as ``/api/method/<dotted.path>``."""
    return any("whitelist" in ast.dump(decorator) for decorator in node.decorator_list)


def _defined_functions() -> dict[str, str]:
    """Every plain module-level function in the portal backend, mapped to its file.

    Whitelisted endpoints are excluded at the source: their caller is a URL, which no reading
    of this repository can count.
    """
    found: dict[str, str] = {}
    for tree in PORTAL_TREES:
        for dirpath, dirs, files in os.walk(os.path.join(_APP, tree)):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for filename in files:
                if not filename.endswith(".py"):
                    continue
                path = os.path.join(dirpath, filename)
                relative = os.path.relpath(path, _APP)
                if _is_test(path):
                    continue
                with open(path, encoding="utf-8") as source:
                    module = ast.parse(source.read())
                for node in module.body:
                    if not isinstance(node, ast.FunctionDef) or node.name.startswith("__"):
                        continue
                    if _is_whitelisted(node):
                        continue
                    found[node.name] = relative
    return found


def _searchable_files() -> list[tuple[str, str]]:
    """Every non-test file a reference could live in, as ``(relative path, text)``."""
    corpus = []
    for dirpath, dirs, files in os.walk(_REPO):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        for filename in files:
            if not filename.endswith(SEARCHED_SUFFIXES):
                continue
            path = os.path.join(dirpath, filename)
            if _is_test(path):
                continue
            try:
                with open(path, encoding="utf-8", errors="ignore") as source:
                    corpus.append((os.path.relpath(path, _APP), source.read()))
            except OSError:
                continue
    return corpus


class TestNoOrphanedPortalHelper(unittest.TestCase):
    def test_the_scan_is_non_vacuous(self):
        """A guard that found no functions would pass for the wrong reason."""
        self.assertGreater(len(_defined_functions()), 100)
        self.assertGreater(len(_searchable_files()), 100)

    def test_every_portal_function_is_referenced_outside_its_own_tests(self):
        defined = _defined_functions()
        corpus = _searchable_files()
        orphans = []
        for name, source in defined.items():
            pattern = re.compile(rf"\b{re.escape(name)}\b")
            hits = 0
            for relative, text in corpus:
                found = len(pattern.findall(text))
                if relative == source:
                    found -= 1  # the definition itself is not a reference
                hits += found
            if hits <= 0:
                orphans.append(f"{name} ({source})")

        self.assertEqual(
            sorted(orphans),
            [],
            "portal-backend functions with no reference outside their own tests — delete them, "
            "or add the module to EXEMPT_MODULES with the reason its names cannot be read "
            "statically:\n  " + "\n  ".join(sorted(orphans)),
        )
