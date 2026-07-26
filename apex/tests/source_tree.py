# Copyright (c) 2026, AFMCO and contributors
"""Source-tree and shipped-artifact queries shared by the static guards.

Frappe-free by construction: that is what lets the site-free guards import it, and
costs the site-bound Arabic ones nothing to import it too.

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
import csv
import glob
import os
import subprocess

APP_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
REPO_ROOT = os.path.dirname(APP_ROOT)
AR_CSV = os.path.join(APP_ROOT, "translations", "ar.csv")


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


def _git_tracked_py_files():
    """apex/**/*.py as CI would receive them, or None when git cannot answer.

    CI grades a fresh clone, so a gitignored file exists only on a developer's
    disk. A guard that walks the filesystem judges it anyway and reds locally
    while CI stays green -- the same asymmetry comment_audit, check_translations
    and check_doctype_dates already avoid with this exact enumeration.
    """
    try:
        out = subprocess.run(
            ["git", "-C", REPO_ROOT, "ls-files", "-z", "--cached", "--others",
             "--exclude-standard", "--", "*.py"],
            capture_output=True,
            check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    prefix = os.path.basename(APP_ROOT) + "/"
    return sorted(
        os.path.join(REPO_ROOT, entry)
        for entry in out.decode().split("\0")
        if entry.startswith(prefix)
    )


def all_py_files():
    """Every apex/**/*.py except node_modules — production AND test."""
    tracked = _git_tracked_py_files()
    if tracked is not None:
        return [path for path in tracked if "node_modules" not in path]
    # No git (an sdist, say): fall back to the walk rather than scanning nothing.
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


def test_support_files():
    """The plain-named shared helper modules under ``tests/`` — factories.py,
    _helpers.py, shipped_doctypes.py, this file.

    Test presence lives here as much as in a ``test_*.py``: a fixture promoted out
    of a test module into factories.py still exercises the production code it
    builds. A coverage scan reading only ``test_*.py`` would score that promotion
    as a LOST test and push the next author back to pasting the body inline.
    """
    return [
        path
        for path in sorted(glob.glob(os.path.join(APP_ROOT, "tests", "*.py")))
        if not os.path.basename(path).startswith("test_")
        and os.path.basename(path) != "__init__.py"
    ]


def translations():
    """``{source: translation}`` from the shipped ar.csv.

    One reader, because two Arabic-coverage guards asking "is this string
    translated?" must not drift apart on what an answered row looks like. A row
    with no second column, or a blank source, answers for nothing.
    """
    rows = {}
    with open(AR_CSV, encoding="utf-8", newline="") as handle:
        for row in csv.reader(handle):
            if len(row) >= 2 and row[0].strip():
                rows[row[0]] = row[1]
    return rows


def func_source(src, path, name):
    """The verbatim source lines of the function ``name`` in ``src``.

    What the source-text guards assert against: they prove a specific line (a lock
    clause, an ignore_permissions flag) sits inside ONE function rather than
    anywhere in the file, which a whole-file substring check cannot tell apart.
    """
    tree = ast.parse(src, filename=path)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            lines = src.splitlines()
            return "\n".join(lines[node.lineno - 1:node.end_lineno])
    raise AssertionError(f"{name} not found in {path}")


def file_dotted_path(path):
    """``<app>.<pkg>...<basename>`` — Frappe's dotted-entrypoint convention. A
    package ``__init__.py`` IS the module, so it resolves to the package path."""
    relpath = os.path.relpath(path, REPO_ROOT)
    if relpath.endswith(os.sep + "__init__.py"):
        relpath = relpath[: -len(os.sep + "__init__.py")]
    else:
        relpath = relpath[: -len(".py")]
    return relpath.replace(os.sep, ".")
