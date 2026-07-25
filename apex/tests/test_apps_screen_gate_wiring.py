# Copyright (c) 2026, AFMCO and contributors
"""Apps-screen gate wiring guard (A-164): no dead or falsely-documented gate helper.

Pure-Python, no live Frappe site required — same family as
test_duplicate_and_dead_code_guard.py and test_release_hygiene.py.

A ``has_apps_screen_access()`` beside a www/ page controller exists for exactly one
reason: to be the ``has_permission`` of that page's tile in hooks.py
``add_to_apps_screen``, so the /apps tile gate cannot drift from the page's own
check. A helper that no tile points at is dead code, and a docstring claiming it
gates a tile it does not is worse than no docstring — that is precisely the defect
this guard was written for (www/fleet.py documented itself as the /fleet tile gate
while the "apex-fleet" tile carried no has_permission at all).

Two directions, so neither half of the wire can rot silently:

  1. TestHelperIsWiredOrMarked — every ``has_apps_screen_access`` defined anywhere
     in production code is EITHER referenced by a tile's has_permission OR declares
     ``retained-unused:`` in its docstring with the reason. Same "justify or don't"
     contract as test_duplicate_and_dead_code_guard.py's ``# native-ok:``. A wired
     helper may NOT also carry the marker — a stale marker left behind after
     someone wires it would lie in the opposite direction.

  2. TestWiredPathResolves — every has_permission dotted path in add_to_apps_screen
     names a module and function that actually exist. Catches the reverse rot: a
     helper renamed or moved out from under a live tile, which would make Frappe
     hide the tile for everyone.

Deliberately NOT a source-text assertion (see the repo's earlier guard that broke on
a safe refactor). The tile side is read by EXECUTING hooks.py and walking the real
``add_to_apps_screen`` list of dicts; the helper side is read from the AST, so both
survive reformatting, reordering, comment edits and quoting changes. Only a genuine
change to the wiring or the marker can move this guard.

hooks.py is loaded by path rather than by ``import apex.hooks`` so the guard runs
identically under bench and standalone, and so a test can point it at a doctored
copy without ever writing to the real hooks.py.

Run standalone:  python3 -m unittest tests.test_apps_screen_gate_wiring -v
"""

import ast
import glob
import importlib.util
import os
import unittest

APP_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
APP_PKG = os.path.basename(APP_ROOT)
HOOKS_PY = os.path.join(APP_ROOT, "hooks.py")

HELPER_NAME = "has_apps_screen_access"
RETAINED_MARKER = "retained-unused:"


def _load_apps_screen(hooks_path=None):
    """Execute hooks.py in isolation and return its real add_to_apps_screen list.

    Structural, not textual: the result is the actual list of dicts Frappe reads.
    """
    path = hooks_path or HOOKS_PY
    spec = importlib.util.spec_from_file_location("_apex_hooks_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return list(getattr(module, "add_to_apps_screen", []))


def _wired_paths(hooks_path=None):
    """Dotted has_permission paths declared by apps-screen tiles."""
    return {
        tile["has_permission"]
        for tile in _load_apps_screen(hooks_path)
        if tile.get("has_permission")
    }


def _dotted(path):
    """apex/www/fleet.py -> apex.www.fleet"""
    rel = os.path.relpath(path, APP_ROOT)
    return ".".join([APP_PKG] + list(os.path.splitext(rel)[0].split(os.sep)))


def _production_py_files():
    out = []
    for path in sorted(glob.glob(os.path.join(APP_ROOT, "**", "*.py"), recursive=True)):
        rel = os.path.relpath(path, APP_ROOT)
        if "node_modules" in path or rel.startswith("tests" + os.sep):
            continue
        if os.path.basename(path).startswith("test_"):
            continue
        out.append(path)
    return out


def _helpers():
    """{dotted_path: docstring_or_empty} for every production has_apps_screen_access."""
    found = {}
    for path in _production_py_files():
        with open(path, encoding="utf-8") as fh:
            try:
                tree = ast.parse(fh.read(), filename=path)
            except SyntaxError:
                continue
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == HELPER_NAME:
                found[f"{_dotted(path)}.{node.name}"] = ast.get_docstring(node) or ""
    return found


def _is_marked(doc):
    return RETAINED_MARKER in doc.lower()


def _unwired_and_unmarked(hooks_path=None):
    """Helpers that back no tile and do not declare themselves retained-unused."""
    wired = _wired_paths(hooks_path)
    return sorted(d for d, doc in _helpers().items() if d not in wired and not _is_marked(doc))


def _wired_but_marked(hooks_path=None):
    """Helpers a tile actually calls that still carry a stale retained-unused marker."""
    wired = _wired_paths(hooks_path)
    return sorted(d for d, doc in _helpers().items() if d in wired and _is_marked(doc))


class TestHelperIsWiredOrMarked(unittest.TestCase):
    def test_scan_finds_helpers(self):
        """Canary: if the scan returns nothing the paths broke and the guard is vacuous."""
        self.assertTrue(_helpers(), f"no {HELPER_NAME} found under {APP_ROOT} — scan path broke")
        self.assertTrue(_wired_paths(), "no apps-screen tile declares has_permission — hooks scan broke")

    def test_every_helper_is_wired_or_marked_retained_unused(self):
        offenders = _unwired_and_unmarked()
        self.assertEqual(
            offenders,
            [],
            "These "
            + HELPER_NAME
            + "() back no add_to_apps_screen tile. Either wire the tile's "
            'has_permission to them, or document why they are kept by starting the '
            'docstring with "' + RETAINED_MARKER + ' <reason>": ' + ", ".join(offenders),
        )

    def test_wired_helper_does_not_claim_retained_unused(self):
        offenders = _wired_but_marked()
        self.assertEqual(
            offenders,
            [],
            'These are wired to a live tile yet still declare "'
            + RETAINED_MARKER
            + '" — drop the stale marker: '
            + ", ".join(offenders),
        )


class TestWiredPathResolves(unittest.TestCase):
    def test_every_wired_has_permission_exists(self):
        """A tile pointing at a missing function makes Frappe hide it for everyone."""
        helpers = _helpers()
        for dotted in sorted(_wired_paths()):
            module_path, _, func = dotted.rpartition(".")
            rel = os.path.join(*module_path.split(".")[1:]) + ".py"
            self.assertTrue(
                os.path.exists(os.path.join(APP_ROOT, rel)),
                f"tile has_permission {dotted} names missing module {rel}",
            )
            self.assertIn(dotted, helpers, f"tile has_permission {dotted} names a function that does not exist")
            self.assertEqual(func, HELPER_NAME, f"unexpected gate function name in {dotted}")


if __name__ == "__main__":
    unittest.main()
