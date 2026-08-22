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

APP_ROOT = str(Path(apex.__file__).resolve().parent)
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
    """Every apex/**/*.py git would ship OR is about to, or None when git cannot answer.

    ``--cached`` is what CI receives. ``--others --exclude-standard`` adds the files
    that are untracked but NOT ignored — a module written and not yet committed — so a
    new file is graded before it lands rather than on the push that lands it. Measured:
    with one uncommitted module present the list is 837 against 836 tracked.

    What both flags exclude is the ignored file, and that exclusion is the point: a
    gitignored module exists only on a developer's disk, so a filesystem walk judges it,
    reds locally, and leaves CI green over a file it never received.
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
    """Every apex/**/*.py except node_modules — production AND test.

    Filtered to paths that EXIST. ``git ls-files`` reads the index, which still lists a
    file deleted on disk until that deletion is staged — so between removing a DocType
    folder and committing it, every caller parsing this list raises FileNotFoundError on
    a file the tree no longer has. The corpus is meant to be the tree, not the index.
    """
    tracked = _git_tracked_py_files()
    if tracked is not None:
        return [
            path
            for path in tracked
            if "node_modules" not in path and os.path.exists(path)
        ]
    return [
        path
        for path in sorted(glob.glob(os.path.join(APP_ROOT, "**", "*.py"), recursive=True))
        if "node_modules" not in path
    ]

def production_py_files():
    """Every apex/**/*.py except tests/ (central or colocated) and node_modules."""
    return [path for path in all_py_files() if not is_test_file(rel(path))]

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

