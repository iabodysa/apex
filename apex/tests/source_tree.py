# Copyright (c) 2026, AFMCO and contributors

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
    return os.path.relpath(path, APP_ROOT)

def parse(path):
    with open(path, encoding="utf-8") as fh:
        try:
            return ast.parse(fh.read(), filename=path)
        except SyntaxError:
            return None

def is_test_file(relpath):
    return relpath.startswith("tests" + os.sep) or os.path.basename(relpath).startswith(
        "test_"
    )

def _git_tracked_py_files():
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
    return [path for path in all_py_files() if not is_test_file(rel(path))]

def translations():
    rows = {}
    with open(AR_CSV, encoding="utf-8", newline="") as handle:
        for row in csv.reader(handle):
            if len(row) >= 2 and row[0].strip():
                rows[row[0]] = row[1]
    return rows

def func_source(src, path, name):
    tree = ast.parse(src, filename=path)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            lines = src.splitlines()
            return "\n".join(lines[node.lineno - 1:node.end_lineno])
    raise AssertionError(f"{name} not found in {path}")

