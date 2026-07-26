# Copyright (c) 2026, AFMCO and contributors
"""Apps-screen gate wiring guard (A-164) + module route-claim guard (A-167):
no dead or falsely-documented gate helper, and no module that documents itself
at a route it does not serve.

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

Third direction — TestModuleRouteClaim (A-167). A module docstring that names a
www route is a claim about a CONSUMER relationship, and that chain is text end to
end: ``www/<route>.html`` names its bundle in a ``<script src>``, the built bundle
under ``public/<bundle>/assets/`` carries the dotted ``apex.…`` endpoint paths it
calls as literals, and Python imports carry the rest. So the guard resolves, per
module, the set of routes that actually reach it, and holds the docstring to it.
The committed bundle is sound evidence because the Portal Bundles workflow reds
if it differs by a byte from a fresh build, so it is what the site really serves.
Five instances of this defect had already been corrected one at a time
(salis/api/fleet_os.py x4, then fleet_reader.py) before it was worth a guard.

Run standalone:  python3 -m unittest apex.tests.test_apps_screen_gate_wiring -v
"""

import ast
import functools
import glob
import importlib.util
import os
import re
import unittest

APP_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
APP_PKG = os.path.basename(APP_ROOT)
HOOKS_PY = os.path.join(APP_ROOT, "hooks.py")
WWW_DIR = os.path.join(APP_ROOT, "www")
PUBLIC_DIR = os.path.join(APP_ROOT, "public")

HELPER_NAME = "has_apps_screen_access"
RETAINED_MARKER = "retained-unused:"

# <script src="/assets/apex/<bundle>/assets/index.js"> in a www shell. Not reusing
# test_portal_route_coverage.served_routes(): it needs PyYAML, which would cost this
# stdlib-only guard its bare-checkout run, and it drops mount-less routes this needs.
BUNDLE_SRC = re.compile(r"/assets/" + APP_PKG + r"/([a-z0-9_]+)/assets/[a-z0-9_.-]+\.js")
# A dotted server path as it survives bundling: minifiers rewrite identifiers but
# never string literals, and no renamed identifier can form an apex.-rooted chain.
DOTTED_API = re.compile(r"\b" + APP_PKG + r"\.[a-z0-9_]+(?:\.[a-z0-9_]+)+")


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
    """apex/www/fleet.py -> apex.www.fleet; a package __init__ names the package."""
    rel = os.path.relpath(path, APP_ROOT)
    parts = list(os.path.splitext(rel)[0].split(os.sep))
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join([APP_PKG] + parts)


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


# A-167 route-claim half: resolve which routes actually reach each module.
@functools.lru_cache(maxsize=1)
def _routes():
    """Every www route, from the template that makes it resolve."""
    return frozenset("/" + os.path.basename(h)[: -len(".html")] for h in glob.glob(os.path.join(WWW_DIR, "*.html")))


@functools.lru_cache(maxsize=1)
def _route_bundles():
    """route -> bundle name, read from the shell's own <script src>."""
    out = {}
    for html in sorted(glob.glob(os.path.join(WWW_DIR, "*.html"))):
        with open(html, encoding="utf-8") as fh:
            found = BUNDLE_SRC.findall(fh.read())
        if found:
            out["/" + os.path.basename(html)[: -len(".html")]] = found[0]
    return out


def _resolve_module(dotted):
    """Longest prefix of a dotted call path that is a real module on disk.

    ``apex.salis.api.fleet_os.get_fleet_os`` -> ``apex.salis.api.fleet_os``. Also
    absorbs the prefix-concatenation form (a trailing ``.`` where the bundle
    appends the method at runtime), which is why only the MODULE half is trusted.
    """
    parts = dotted.split(".")
    for n in range(len(parts), 1, -1):
        base = os.path.join(APP_ROOT, *parts[1:n])
        if os.path.isfile(base + ".py") or os.path.isfile(os.path.join(base, "__init__.py")):
            return ".".join(parts[:n])
    return None


@functools.lru_cache(maxsize=1)
def _bundle_modules():
    """bundle -> the app modules its built assets call.

    Every ``.js`` in the bundle dir is scanned, not just the entry chunk the shell
    names: worker_portal is code-split and its index.js carries ZERO dotted paths,
    so an entry-only scan would report that bundle as calling nothing.
    """
    out = {}
    for bundle in sorted(os.listdir(PUBLIC_DIR)) if os.path.isdir(PUBLIC_DIR) else []:
        assets = os.path.join(PUBLIC_DIR, bundle, "assets")
        if not os.path.isdir(assets):
            continue
        mods = set()
        for js in sorted(glob.glob(os.path.join(assets, "**", "*.js"), recursive=True)):
            with open(js, encoding="utf-8", errors="replace") as fh:
                for hit in DOTTED_API.findall(fh.read()):
                    resolved = _resolve_module(hit)
                    if resolved:
                        mods.add(resolved)
        out[bundle] = mods
    return out


@functools.lru_cache(maxsize=1)
def _module_docstrings():
    """dotted module -> its module docstring, for every production module."""
    out = {}
    for path in _production_py_files():
        with open(path, encoding="utf-8") as fh:
            try:
                tree = ast.parse(fh.read(), filename=path)
            except SyntaxError:
                continue
        out[_dotted(path)] = ast.get_docstring(tree) or ""
    return out


@functools.lru_cache(maxsize=1)
def _intra_app_imports():
    """dotted module -> the app modules it imports, so a shared module inherits
    the routes of every module that pulls it in."""
    known = set(_module_docstrings())
    out = {}
    for path in _production_py_files():
        with open(path, encoding="utf-8") as fh:
            try:
                tree = ast.parse(fh.read(), filename=path)
            except SyntaxError:
                continue
        edges = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith(APP_PKG + "."):
                edges.add(node.module)
                # `from pkg import submodule` is an edge to the submodule too.
                edges.update(node.module + "." + alias.name for alias in node.names)
            elif isinstance(node, ast.Import):
                edges.update(a.name for a in node.names if a.name.startswith(APP_PKG + "."))
        out[_dotted(path)] = edges & known
    return out


@functools.lru_cache(maxsize=1)
def _routes_by_module():
    """dotted module -> the routes that actually reach it.

    Forward closure from each route's bundle over the import graph, plus the www
    controller that serves the route directly.
    """
    imports = _intra_app_imports()
    bundles = _bundle_modules()
    reached = {}
    for route, bundle in _route_bundles().items():
        seen, stack = set(), list(bundles.get(bundle, ()))
        while stack:
            mod = stack.pop()
            if mod in seen:
                continue
            seen.add(mod)
            stack.extend(imports.get(mod, ()))
        for mod in seen:
            reached.setdefault(mod, set()).add(route)
    known = set(_module_docstrings())
    for route in _routes():
        controller = f"{APP_PKG}.www." + route.lstrip("/").replace("-", "_")
        if controller in known:
            reached.setdefault(controller, set()).add(route)
    return reached


@functools.lru_cache(maxsize=1)
def _route_token():
    """Longest-first alternation so /fleet never matches inside /fleet-os."""
    alts = "|".join(re.escape(r[1:]) for r in sorted(_routes(), key=len, reverse=True))
    return re.compile(r"(?<![\w-])/(" + alts + r")(?![\w-])")


def _named_routes(doc):
    return {"/" + m.group(1) for m in _route_token().finditer(doc)}


def _route_claim_offenders(docstrings=None):
    """Modules a bundle reaches whose docstring names ONLY routes it never serves.

    Deliberately weak in one direction (see the class docstring): naming at least
    one route it does serve is enough. That is what keeps it free of false
    positives on disambiguation and sibling cross-references, and it is the exact
    signature every instance of this defect has had.
    """
    reached = _routes_by_module()
    docs = _module_docstrings() if docstrings is None else docstrings
    offenders = []
    for mod in sorted(docs):
        serves = reached.get(mod)
        if not serves:
            continue
        named = _named_routes(docs[mod])
        if named and not (named & serves):
            offenders.append((mod, sorted(named), sorted(serves)))
    return offenders


class TestModuleRouteClaim(unittest.TestCase):
    """A module docstring may not place the module at a route no consumer of it loads.

    Checked ONLY for modules some bundle transitively reaches, because only those
    have a traceable consumer chain. Three scopes are therefore out of reach and
    stay unchecked ON PURPOSE, each for a stated reason:

      * a module no bundle calls (a DocType controller, a patch, a Desk-Page-only
        API) has no bundle to trace, so its route mention is unfalsifiable here;
      * method granularity, because a bundle may concatenate the method onto a
        literal module prefix at runtime — only the module half survives as text;
      * a docstring that names its real route AND a wrong one in a claim position,
        which passes.

    That last one is a deliberate trade, measured rather than assumed. Tightening
    it to "every route mentioned must be reachable" flagged, on the tree that
    still held the three defects, 10 unreachable mentions across 8 modules that
    were all legitimate — sibling cross-references between portal controllers, a
    redirect target, and fleet_os.py's own "NOT ``/fleet``" disambiguation. Worse,
    on the CORRECTED tree it would flag 13 mentions across 11 modules and zero
    defects, because a docstring that fixes this bug names the wrong route on
    purpose to warn the next reader off it. The strict form would therefore
    punish the fix. The weak form separates the two sets exactly, with no marker
    convention to keep up.
    """

    def test_scans_are_not_vacuous(self):
        """Canary: any broken path here would silently pass every assertion below."""
        self.assertTrue(_route_bundles(), "no www shell names a bundle — the shell scan broke")
        self.assertTrue(
            any(_bundle_modules().get(b) for b in _route_bundles().values()),
            "no routed bundle references an app module — the bundle scan broke",
        )
        self.assertTrue(_routes_by_module(), "no module is reachable from a route — the closure broke")

    def test_no_module_claims_a_route_it_does_not_serve(self):
        offenders = _route_claim_offenders()
        self.assertEqual(
            offenders,
            [],
            "These module docstrings name a www route that no consumer of the module loads. "
            "Trace the route: www/<route>.html names the bundle, and the built bundle under "
            "public/<bundle>/assets/ names the modules it calls. "
            + "; ".join(f"{mod} says {named} but is reached from {serves}" for mod, named, serves in offenders),
        )

    def test_guard_reds_on_a_wrong_docstring(self):
        """Failure proof: the real trace, with one docstring doctored in memory back
        to the /fleet claim this guard was written for."""
        target = APP_PKG + ".salis.api.fleet_reader"
        docs = dict(_module_docstrings())
        self.assertIn(target, docs, "fleet_reader moved — repoint this proof")
        docs[target] = "Shared fleet-reader service for the /fleet SPA."
        self.assertEqual([mod for mod, _named, _serves in _route_claim_offenders(docs)], [target])

    def test_a_correct_docstring_is_not_flagged(self):
        """The other half of the proof: the corrected claim passes the same trace."""
        target = APP_PKG + ".salis.api.fleet_reader"
        docs = dict(_module_docstrings())
        docs[target] = "Shared fleet-reader service for the /fleet-os SPA (NOT /fleet)."
        self.assertEqual(_route_claim_offenders(docs), [])


if __name__ == "__main__":
    unittest.main()
