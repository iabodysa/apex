# Copyright (c) 2026, AFMCO and contributors
"""Guard (A-147): a www controller with no template serves a 404, not a page.

A ``.py`` under ``apex/www/`` is NEVER a route on its own. ``TemplatePage``
resolves a request by looking for a TEMPLATE file and nothing else:
``set_template_path`` (frappe/website/page_renderers/template_page.py:47-68)
tries only the five forms ``get_index_path_options`` yields (line 77-81) --
``<route>``, ``<route>.html``, ``<route>.md``, ``<route>/index.html``,
``<route>/index.md`` -- and ``can_render`` (line 70-75) additionally refuses any
Python suffix. The controller is discovered only LATER, by ``set_pymodule``
(line 131-147), from the template that was already found, mapping hyphens in the
template name to underscores in the module name.

The consequence that makes this worth a guard: ``get_context`` in a
template-less controller is UNREACHABLE. ``get_html`` calls ``set_pymodule`` and
``update_context`` (line 94-95), but ``get_html`` only runs after ``can_render``
returned True. So a controller whose whole body is a redirect looks like a
working redirect in review and is dead code at runtime -- ``PathResolver.resolve``
falls through every renderer to ``NotFoundPage`` (path_resolver.py:67-72) and the
route answers 404.

That was exactly the state ``www/housing_count.py`` was in, and the ``Inventory
Count`` shortcut in the Housing workspace points straight at it. A-174 fixed it
by adding the sibling ``www/housing-count.html`` marker, so both baselines below
are now EMPTY and the guard runs at zero tolerance.

The route-reachability half of the guard closes the same gap from the other
side: a workspace shortcut that names a portal route apex/www does not serve is
a dead tile, and nothing else in the suite compares those two lists.
"""

import ast
import json
import unittest
from pathlib import Path

from frappe.website.page_renderers.template_page import PY_LOADER_SUFFIXES, TemplatePage

WWW = Path(__file__).resolve().parent
APP_ROOT = WWW.parent

# The servable suffixes get_index_path_options offers. "" is the extensionless
# form; the two `/index.*` forms need no entry here because a controller for them
# sits INSIDE the route directory, which the per-directory scan already walks.
TEMPLATE_SUFFIXES = ("", ".html", ".md")

# A Desk route is served by the Desk bundle, not by apex/www.
DESK_PREFIX = "/app"


def _defines_get_context(path: Path) -> bool:
    """True if the module binds a top-level ``get_context`` -- i.e. it is a page
    controller rather than a helper or a colocated test."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "get_context"
        for node in tree.body
    )


def _page_controllers(root: Path) -> list[Path]:
    controllers = []
    for path in sorted(root.rglob("*.py")):
        if path.name == "__init__.py" or path.name.startswith("test_"):
            continue
        if _defines_get_context(path):
            controllers.append(path)
    return controllers


def _templates_binding_to(controller: Path) -> list[Path]:
    """Sibling files whose ``set_pymodule`` mapping resolves back to ``controller``.

    Mirrors template_page.py:137-144 in reverse: the module name is the template
    basename with hyphens replaced by underscores."""
    stem = controller.stem
    found = []
    for sibling in sorted(controller.parent.iterdir()):
        if not sibling.is_file() or sibling.suffix not in TEMPLATE_SUFFIXES:
            continue
        if sibling.name.endswith(PY_LOADER_SUFFIXES):
            continue
        if sibling.stem.replace("-", "_") == stem:
            found.append(sibling)
    return found


def _templateless(root: Path) -> list[str]:
    """Offenders under ``root``, named relative to its parent so the app scan
    reports ``www/<module>.py`` and a temp-dir scan stays self-relative."""
    return [
        str(controller.relative_to(root.parent))
        for controller in _page_controllers(root)
        if not _templates_binding_to(controller)
    ]


def _served_routes() -> set[str]:
    """Route names apex/www can actually serve, derived the way the resolver
    finds them: one entry per template file, hyphens preserved."""
    routes = set()
    for path in WWW.rglob("*"):
        if not path.is_file() or path.suffix not in (".html", ".md"):
            continue
        relative = path.relative_to(WWW)
        routes.add(str(relative.parent) if path.stem == "index" else str(relative.with_suffix("")))
    return routes


def _workspace_shortcut_urls() -> list[tuple[str, str]]:
    """(workspace file, url) for every URL-type shortcut in every shipped workspace."""
    out = []
    for path in sorted(APP_ROOT.glob("*/workspace/*/*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for shortcut in data.get("shortcuts") or []:
            if shortcut.get("type") == "URL" and shortcut.get("url"):
                out.append((str(path.relative_to(APP_ROOT)), shortcut["url"]))
    return out


def _dead_shortcuts(shortcuts, served) -> list[str]:
    """Shortcut urls whose route name is absent from ``served``."""
    return sorted({url for _, url in shortcuts if url.lstrip("/").split("?")[0].split("#")[0] not in served})


def _portal_shortcuts() -> list[tuple[str, str]]:
    """Shortcuts that name a root-relative apex/www route (not a Desk route)."""
    return [
        (source, url)
        for source, url in _workspace_shortcut_urls()
        if url.startswith("/") and not url.startswith(DESK_PREFIX + "/") and url != DESK_PREFIX
    ]


# [#a147r1] Emptied by A-174. SHRINK-ONLY: an entry leaves when the route is fixed,
# and test_frozen_offenders_are_still_broken fails if one is fixed but not pruned.
# Adding an entry is a review decision, never a way to ship a new one.
_TEMPLATELESS_BASELINE: dict[str, str] = {}

# [#a147r2] Shortcut targets no www template serves. Same shrink-only rule.
_DEAD_SHORTCUT_BASELINE: set[str] = set()


class TestFrameworkNeverServesABareController(unittest.TestCase):
    """Sentinel: the premise this guard rests on, asserted against frappe itself."""

    def test_no_index_path_option_is_a_python_module(self):
        options = list(TemplatePage.get_index_path_options("/apex/www/housing-count"))
        self.assertEqual(len(options), 5, f"the resolver option list changed: {options}")
        self.assertEqual(
            [o for o in options if o.endswith(PY_LOADER_SUFFIXES)],
            [],
            "TemplatePage would now resolve a Python module directly, which would "
            f"make this whole guard moot -- re-read template_page.py:77-81: {options}",
        )

    def test_can_render_refuses_a_python_template_path(self):
        self.assertTrue("www/housing_count.py".endswith(PY_LOADER_SUFFIXES))
        self.assertFalse("www/housing-count.html".endswith(PY_LOADER_SUFFIXES))

    def test_underscored_module_binds_to_the_hyphenated_template(self):
        # The mapping that makes fleet_os.py the controller for fleet-os.html.
        self.assertEqual("fleet-os".replace("-", "_"), "fleet_os")
        self.assertTrue((WWW / "fleet-os.html").is_file())
        self.assertEqual(
            [p.name for p in _templates_binding_to(WWW / "fleet_os.py")],
            ["fleet-os.html"],
            "the hyphen/underscore mapping broke, so every hyphenated route would "
            "be reported as template-less",
        )


class TestDetector(unittest.TestCase):
    """Failure proof: the scan must red on a synthetic offender."""

    def _write(self, tmp: Path, name: str, body: str = "def get_context(context):\n    pass\n"):
        (tmp / name).write_text(body, encoding="utf-8")

    def test_flags_a_controller_with_no_template_and_accepts_one_with_a_template(self):
        import tempfile

        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            self._write(tmp, "orphan_page.py")
            self._write(tmp, "paired_page.py")
            (tmp / "paired-page.html").write_text("<p>x</p>", encoding="utf-8")
            offenders = [Path(o).name for o in _templateless(tmp)]
            self.assertEqual(
                offenders,
                ["orphan_page.py"],
                "the detector must flag exactly the template-less controller",
            )

    def test_a_helper_module_without_get_context_is_not_a_controller(self):
        import tempfile

        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            self._write(tmp, "helpers.py", "def build(x):\n    return x\n")
            self.assertEqual(_page_controllers(tmp), [])


class TestWwwControllersHaveTemplates(unittest.TestCase):
    def test_scan_finds_the_www_controllers(self):
        controllers = _page_controllers(WWW)
        self.assertGreaterEqual(
            len(controllers),
            8,
            f"www controller scan returned implausibly few files: {controllers}",
        )

    def test_no_new_templateless_www_controller(self):
        new = sorted(set(_templateless(WWW)) - set(_TEMPLATELESS_BASELINE))
        self.assertEqual(
            new,
            [],
            "www controller(s) with no template Frappe can resolve. get_context "
            "will never run and the route answers 404 "
            "(template_page.py:70-75 + path_resolver.py:67-72). Add a sibling "
            "<route>.html, or serve the surface from a route that has one:\n  "
            + "\n  ".join(new),
        )

    def test_housing_count_is_reachable_so_its_redirect_can_run(self):
        # The A-174 fix, asserted along the resolver's own chain: a non-Python
        # template exists, set_pymodule maps it back to the controller, and the
        # route appears in the served set the shortcut check compares against.
        template = WWW / "housing-count.html"
        self.assertTrue(template.is_file(), "the marker template is gone -- /housing-count 404s again")
        self.assertFalse(template.name.endswith(PY_LOADER_SUFFIXES))
        self.assertEqual(
            [p.name for p in _templates_binding_to(WWW / "housing_count.py")],
            ["housing-count.html"],
        )
        self.assertIn("housing-count", _served_routes())

    def test_frozen_offenders_are_still_broken(self):
        fixed = sorted(set(_TEMPLATELESS_BASELINE) - set(_templateless(WWW)))
        self.assertEqual(
            fixed,
            [],
            "a frozen template-less controller now HAS a template -- prune it from "
            "_TEMPLATELESS_BASELINE so the ratchet keeps shrinking:\n  "
            + "\n  ".join(fixed),
        )


class TestWorkspaceShortcutsResolve(unittest.TestCase):
    def test_scan_finds_the_portal_shortcuts(self):
        shortcuts = _portal_shortcuts()
        self.assertGreaterEqual(
            len(shortcuts),
            5,
            f"workspace shortcut scan returned implausibly few entries: {shortcuts}",
        )
        self.assertGreaterEqual(len(_served_routes()), 7, "www route scan found too little")

    def test_detector_flags_an_unserved_shortcut_and_accepts_a_served_one(self):
        served = {"housing", "safety"}
        probe = [("w.json", "/housing"), ("w.json", "/housing-count"), ("w.json", "/safety#/x")]
        self.assertEqual(_dead_shortcuts(probe, served), ["/housing-count"])

    def test_every_portal_shortcut_points_at_a_route_www_serves(self):
        dead = _dead_shortcuts(_portal_shortcuts(), _served_routes())
        new = [url for url in dead if url not in _DEAD_SHORTCUT_BASELINE]
        self.assertEqual(
            new,
            [],
            "workspace shortcut(s) pointing at a route no www template serves -- the "
            f"tile opens a 404: {new}",
        )

    def test_frozen_dead_shortcuts_are_still_dead(self):
        served = _served_routes()
        revived = sorted(
            url for url in _DEAD_SHORTCUT_BASELINE if url.lstrip("/").split("?")[0] in served
        )
        self.assertEqual(
            revived,
            [],
            "a frozen dead shortcut now resolves -- prune it from "
            f"_DEAD_SHORTCUT_BASELINE: {revived}",
        )


if __name__ == "__main__":
    unittest.main()
