# Copyright (c) 2026, AFMCO and contributors
"""Guard: a seeder docstring may not name a Python/JSON artifact that is absent.

A-264 found four of these in this one package at once: the workflow base named a
third module seeder (``logistay_workflow_seed``) archived with the Logistay v1
engine, the dashboard seeder named a run-once patch pruned as spent, and two
seeders said they mirrored a sibling whose path had moved or whose file was
retired for native JSON. Each one sends the next reader hunting a file that was
deliberately removed, and nothing on the tree said otherwise -- prose is the one
place a rename does not break a build.

Scope is this package, not the whole app: the defect clustered here (4/4), and a
tree-wide sweep of every backticked token is a different, much larger job.

Deliberately NOT "every dotted path in a docstring must import". That form is
unusable here -- it fires on framework symbols the seeders legitimately cite
(``frappe.model.sync.IMPORTABLE_DOCTYPES``, ``_validate_links``), on field
references (``Service Level Agreement.holiday_list``), and on inline literals.
Instead only tokens that unambiguously name a shipped artifact are resolved: a
``.py``/``.json`` path, a ``patches/`` entry, or a bare ``*_seed`` module name.
Placeholders (anything with ``<``) and prose are skipped, so the guard stays
quiet unless a real filename has gone stale.

Frappe-free: it reads the source tree only, so it runs without a site.

Run standalone (from the repo root, so ``apex.tests.source_tree`` resolves):
    python3 -m unittest apex.apex_core.setup.seeders.test_seeder_docstring_references
"""

import ast
import glob
import os
import re
import tokenize
import unittest

from apex.tests.source_tree import APP_ROOT, REPO_ROOT, parse, rel

SEEDERS_DIR = os.path.dirname(os.path.abspath(__file__))

# A backticked token only counts as an artifact reference in one of these shapes.
_PATH_SUFFIXES = (".py", ".json")
_BARE_MODULE = re.compile(r"^[a-z0-9_]+_seed(_base)?$")


def _seeder_py_files():
    """Every seeder module except this one -- the guard's own prose quotes the
    retired names it exists to reject, so scanning itself always reds."""
    return [
        path
        for path in sorted(glob.glob(os.path.join(SEEDERS_DIR, "*.py")))
        if os.path.abspath(path) != os.path.abspath(__file__)
    ]


def _prose(path):
    """Every docstring and comment in ``path`` as ``(lineno, text)``."""
    tree = parse(path)
    if tree is None:
        return []
    out = []
    for node in ast.walk(tree):
        if isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            text = ast.get_docstring(node)
            if text:
                out.append((getattr(node, "lineno", 1), text))
    with open(path, encoding="utf-8") as handle:
        for token in tokenize.generate_tokens(handle.readline):
            if token.type == tokenize.COMMENT:
                out.append((token.start[0], token.string))
    return out


def _artifact_tokens(text):
    """The ``backticked`` tokens in ``text`` that name a shipped artifact."""
    for match in re.finditer(r"``([^`]+)``", text):
        token = match.group(1).strip()
        # A placeholder or a prose fragment names nothing resolvable.
        if "<" in token or any(ch.isspace() for ch in token):
            continue
        # A bare suffix (".py") is prose about file kinds, not a filename.
        if token.startswith("."):
            continue
        if token.endswith(_PATH_SUFFIXES) or token.startswith("patches/"):
            yield token
        elif _BARE_MODULE.match(token):
            yield token


def _resolves(token):
    """True if ``token`` points at a file that ships in the tree."""
    if _BARE_MODULE.match(token) and not token.endswith(_PATH_SUFFIXES):
        token += ".py"
    # Cited relative to the repo root, to the app root, or as a bare basename.
    for base in (REPO_ROOT, APP_ROOT):
        for candidate in (token, token + ".py"):
            if os.path.exists(os.path.join(base, candidate)):
                return True
    basename = os.path.basename(token)
    if basename != token or token.endswith(_PATH_SUFFIXES):
        pattern = os.path.join(APP_ROOT, "**", basename)
        if any(glob.glob(pattern, recursive=True)):
            return True
    return False


class TestSeederDocstringReferences(unittest.TestCase):
    def test_every_named_artifact_exists(self):
        """A seeder naming a file, patch or module must name one that is there."""
        stale = []
        for path in _seeder_py_files():
            for lineno, text in _prose(path):
                for token in _artifact_tokens(text):
                    if not _resolves(token):
                        stale.append(f"{rel(path)}:{lineno} names `{token}`")
        self.assertEqual(
            stale,
            [],
            "seeder prose names artifacts that are not in the tree "
            "(delete the reference or point it at what replaced it):\n  "
            + "\n  ".join(stale),
        )

    def test_the_guard_can_see_a_bad_name(self):
        """The detector itself, proven on a planted reference. Without this, a
        pattern that silently matches nothing would pass the guard above."""
        planted = 'Mirrors ``logistay_workflow_seed`` and ``patches/v9_9/gone.py``.'
        found = list(_artifact_tokens(planted))
        self.assertEqual(found, ["logistay_workflow_seed", "patches/v9_9/gone.py"])
        self.assertFalse(any(_resolves(token) for token in found))

    def test_a_live_reference_still_resolves(self):
        """The other half: real names must not be reported as stale."""
        for token in ("salis_issue_seed", "patches/v0_8/add_navbar_help_links.py"):
            self.assertTrue(_resolves(token), token)
