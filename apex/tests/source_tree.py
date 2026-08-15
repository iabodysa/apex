# Copyright (c) 2026, AFMCO and contributors
"""Source-tree and shipped-artifact queries shared by the colocated tests.

Frappe-free by construction, so a test that needs no site can import it without
paying for one.

Deliberately NOT named ``test_*``: a plain-named ``tests/`` helper is the sanctioned
shape for shared test logic (the same reason factories.py and shipped_doctypes.py
carry plain names).
"""

import ast
import csv
import glob
import os
import subprocess
from pathlib import Path

import apex

# The INSTALLED package, never this file's own neighbourhood. The suite moved out of the
# app on 2026-08-02, so `dirname(__file__)/..` named `.claude/tests/apex`, a tree holding
# nothing but test modules: every source scan read through here graded an empty file list
# and passed, and the translation reader died on an ar.csv that is not there.
APP_ROOT = str(Path(apex.__file__).resolve().parent)
REPO_ROOT = os.path.dirname(APP_ROOT)
AR_CSV = os.path.join(APP_ROOT, "translations", "ar.csv")

# The maintainer mirror, named from the repo and NEVER from this file's own
# neighbourhood. This module was written at `.claude/tests/apex/tests/`, where
# `dirname(__file__)/../..` did name the mirror; it now ships at `apex/tests/`, where the
# same expression names the repo root and SUITE_PACKAGE comes out equal to APP_ROOT. Both
# readers below then answer about the app alone, which is the empty-mirror half of the
# failure the comment above describes. Absent on a fresh clone, and that is fine: the
# readers fall back to the shipped corpus rather than to nothing.
SUITE_ROOT = os.path.join(REPO_ROOT, ".claude", "tests")
SUITE_PACKAGE = os.path.join(SUITE_ROOT, "apex")

# Package/script CDNs, then font CDNs; a page or bundle needing one needs a vendored copy.
# One home because the shell scan and the bundle scan both read it, and two hand-kept
# copies meant a host added to one left the other blind. gstatic is listed even though it
# never appears in markup alone: a preconnect to it is how these shells warmed the
# third-party connection.
CDN_HOSTS = (
    "unpkg.com",
    "unpkg.io",
    "cdn.jsdelivr.net",
    "jsdelivr.net",
    "cdnjs.cloudflare.com",
    "ajax.googleapis.com",
    "code.jquery.com",
    "stackpath.bootstrapcdn.com",
    "maxcdn.bootstrapcdn.com",
    "esm.sh",
    "cdn.skypack.dev",
    "fonts.googleapis.com",
    "fonts.gstatic.com",
    "use.typekit.net",
    "fonts.bunny.net",
)


def rel(path):
    """``path`` relative to the app root (``apex/``)."""
    return os.path.relpath(path, APP_ROOT)


def suite_rel(path):
    """``path`` named against whichever root holds it, for naming a TEST module.

    The corpus spans two roots: a module beside its unit under the app, and a module
    in the maintainer mirror. ``rel`` on a mirror module yields a ``../.claude/...``
    string that no reader recognises and no allowlist matches, so the innermost
    containing root wins and the name comes out the way its own runner spells it.
    """
    for root in (APP_ROOT, SUITE_PACKAGE, SUITE_ROOT):
        if path.startswith(root + os.sep):
            return os.path.relpath(path, root)
    return os.path.relpath(path, REPO_ROOT)


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
    while CI stays green -- the same asymmetry the maintainer's own audit scripts
    avoid with this exact enumeration.
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
    """Every test_*.py in the corpus — the shipped modules beside their unit AND the
    maintainer mirror (its tree and its root).

    Both roots, because the corpus is split across both and a guard that scans test
    modules for a defect has to see all of them. Reading only one root is how the
    same floor keeps passing over a population that changed underneath it.
    """
    paths = set()
    for root in (APP_ROOT, SUITE_ROOT):
        paths.update(glob.glob(os.path.join(root, "**", "test_*.py"), recursive=True))
    return sorted(
        path
        for path in paths
        if "node_modules" not in path and "__pycache__" not in path
    )


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
