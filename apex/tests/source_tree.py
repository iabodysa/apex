# Copyright (c) 2026, AFMCO and contributors
"""Source-tree queries shared by the site-free static guards.

test_duplicate_and_dead_code_guard.py and test_unit_test_coverage_guard.py each
grew their own ``_production_py_files`` and ``_file_dotted_path``, so the widened
copy-paste detector caught the guard family duplicating itself on its first day.
One home instead: the two guards read each other's baselines, so their scan
universes drifting apart would make one guard's verdict meaningless to the other.

Deliberately NOT named ``test_*``: tests/test_no_cross_test_imports.py bans a test
module importing a sibling test module, and a plain-named ``tests/`` helper is the
sanctioned shape for shared test logic (the same reason factories.py and
shipped_doctypes.py carry plain names).
"""

import ast
import glob
import os

APP_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
REPO_ROOT = os.path.dirname(APP_ROOT)


def rel(path):
    """``path`` relative to the app root (``apex/``)."""
    return os.path.relpath(path, APP_ROOT)


def parse(path):
    """The file's AST, or None when it does not parse — a static guard reports
    what it can read rather than dying on one malformed neighbour."""
    with open(path, encoding="utf-8") as fh:
        try:
            return ast.parse(fh.read(), filename=path)
        except SyntaxError:
            return None


def is_test_file(relpath):
    """A central ``tests/`` module or a colocated ``test_*.py`` beside its unit."""
    return relpath.startswith("tests" + os.sep) or os.path.basename(relpath).startswith(
        "test_"
    )


def all_py_files():
    """Every apex/**/*.py except node_modules — production AND test."""
    return [
        path
        for path in sorted(glob.glob(os.path.join(APP_ROOT, "**", "*.py"), recursive=True))
        if "node_modules" not in path
    ]


def production_py_files():
    """Every apex/**/*.py except tests/ (central or colocated) and node_modules."""
    return [path for path in all_py_files() if not is_test_file(rel(path))]


def test_py_files():
    """Every test_*.py anywhere under apex/ — central apex/tests/ AND colocated."""
    return [
        path
        for path in sorted(
            glob.glob(os.path.join(APP_ROOT, "**", "test_*.py"), recursive=True)
        )
        if "node_modules" not in path
    ]


def file_dotted_path(path):
    """``<app>.<pkg>...<basename>`` — Frappe's dotted-entrypoint convention. A
    package ``__init__.py`` IS the module, so it resolves to the package path."""
    relpath = os.path.relpath(path, REPO_ROOT)
    if relpath.endswith(os.sep + "__init__.py"):
        relpath = relpath[: -len(os.sep + "__init__.py")]
    else:
        relpath = relpath[: -len(".py")]
    return relpath.replace(os.sep, ".")
