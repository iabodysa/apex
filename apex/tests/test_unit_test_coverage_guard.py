# Copyright (c) 2026, AFMCO and contributors
"""Unit-test coverage ratchet guard (A-108 Phase 0).

Pure-Python, no live Frappe site required — same family as
test_duplicate_and_dead_code_guard.py, test_release_hygiene.py,
test_sql_interpolation_guard.py and test_no_cross_test_imports.py.
Its source-tree queries come from ``tests/source_tree.py``, the plain-named
shared home this guard family uses — never from a sibling ``test_*.py`` module,
which test_no_cross_test_imports.py's now-EMPTY baseline forbids outright.
They used to be reimplemented locally, which is how this guard ended up
duplicating the very code the sibling duplication guard scans for (A-176).

Policy
------
Four classes of "must-test" production unit, each chosen to be a narrow,
low-false-positive proxy for "this file carries real logic":

  1. API module — a file under a directory literally named ``api`` anywhere
     in its path (``salis/api/fleet_employee.py``,
     ``salis/api/driver_portal/fuel.py``, ...) that binds at least one
     ``@frappe.whitelist(...)`` endpoint (HTTP-reachable).
  2. Non-trivial DocType controller — ``<module>/doctype/<slug>/<slug>.py``
     with more than ~10 non-blank, non-comment source lines. This excludes
     the ubiquitous bare ``class X(Document): pass`` stub carrying no hooks
     (see test_duplicate_and_dead_code_guard.py's module docstring on this
     codebase's "detached controller" style) while still catching a
     controller whose module-level hooks (``before_save``, ``on_submit``,
     ...) hold real logic.
  3. Utils module — a file under a directory literally named ``utils``, or
     literally named ``utils.py``, defining at least one PUBLIC
     (non-underscore) top-level function. Covers a package's
     ``utils/__init__.py`` when THAT file is itself the module (this
     codebase does this — e.g. ``salis/utils/__init__.py`` defines
     ``get_driver_for_user`` directly), not just a plain ``utils/x.py``.
  4. Report controller — ``<module>/report/<slug>/<slug>.py`` defining a
     module-level ``execute`` function.

"Covered" — deliberately permissive, several independent signals
------------------------------------------------------------------
A unit is "covered" if ANY of the following holds, checked against every
``test_*.py`` file anywhere under apex/ (central ``apex/tests/`` AND any
already-colocated file — A-108 Phase 1 relocates the former into the latter;
this guard must recognise coverage in either home):

  a) a ``test_<name>.py`` file sits in the SAME DIRECTORY (true colocation;
     for a package ``__init__.py`` that is itself the module, ``<name>`` is
     the parent directory's name, since '__init__' alone is meaningless);
  b) some test statically imports the module's dotted path
     (``import apex.x.y`` / ``from apex.x.y import z``) or mentions it as a
     literal quoted string (``frappe.get_attr("apex.x.y.z")``);
  c) [DocType controllers only] the DocType's declared human ``name`` (from
     its sibling ``<slug>.json``) appears as a quoted string in some test —
     Frappe ORM tests key doctypes by NAME (``frappe.get_doc({"doctype":
     "X", ...})``), never by importing the controller module, so this is
     the dominant real coverage signal for a "detached controller";
  d) [API / utils only] one of the module's own whitelisted/public function
     names is called (``name(``) somewhere — this is what catches a function
     re-exported and called off its PARENT package instead of its own
     module: ``salis/api/driver_portal/attendance.py``'s own module
     docstring says its helpers are "imported from the package so the
     canonical dotted path apex.salis.api.driver_portal.<fn> stays
     unchanged", and indeed its test calls ``driver_portal.my_attendance()``
     — the substring "attendance" never appears anywhere in that test, only
     the bare function name does;
  e) [report only] the report's bare basename appears as a quoted string —
     catches a dynamic sweep test that loads reports by name from a list
     constant (``frappe.get_module(f"...{report_module}...")``): the
     f-string itself is never a static dotted reference, but the basename is
     a literal list element (confirmed live: test_qa_probe_systems.py's
     ``TestReports.REPORTS`` sweep is exactly this shape).

None of this proves DEEP behavioural coverage (a fixture doctype referenced
by name might never actually exercise its own before_save/on_update path) —
that would need a live coverage.py run against a real site, out of reach for
a static, no-bench guard. The trade-off is deliberate and matches this
guard's mandate: a false NEGATIVE here (says covered, isn't deeply exercised)
is cheap; a false POSITIVE (blocks/annoys over something that already has a
real test, just not in the shape this guard expected) is the one this file
works hard to avoid — see the five signals above, each added after finding a
real false positive while calibrating against this tree.

Ratchet
-------
Exactly like test_no_cross_test_imports.py's ``_BASELINE`` and
test_duplicate_and_dead_code_guard.py's ``_DUP_NAME_BASELINE``: today's gaps
are frozen in ``_BASELINE`` below (confirmed by hand, one at a time, while
authoring this guard — genuinely zero test presence in any shape). Fixing
one is A-108 Phase 2's job, out of scope here; this guard only fails when the
uncovered set grows BEYOND the frozen baseline, i.e. when NEW production code
ships with no test anywhere in the tree.

Run standalone (from the repo root, so ``apex.tests.source_tree`` resolves):
  python3 -m unittest apex.tests.test_unit_test_coverage_guard -v
"""

import ast
import json
import os
import re
import unittest

from apex.tests.source_tree import (
    APP_ROOT,
    REPO_ROOT,
    file_dotted_path as _file_dotted_path,
    parse as _parse,
    production_py_files as _production_py_files,
    rel as _rel,
    test_py_files as _test_py_files,
)

# [#a108rx] Dotted apex.<...> references mentioned as plain TEXT anywhere in a
# test file (a `frappe.get_attr("apex.x.y.z")`-style literal string, or a
# hooks-like dotted method path) — mirrors test_duplicate_and_dead_code_guard
# .py's `_DOTTED_RE`, narrowed to just the `apex` prefix (apex_habitat was
# retired 2026-07).
_DOTTED_RE = re.compile(r"\bapex(?:\.[A-Za-z_][A-Za-z0-9_]*)+")


def _module_basename(path):
    """The name a SAME-DIRECTORY 'test_<name>.py' would be expected to carry.

    A package ``__init__.py`` IS the module in this codebase's style (e.g.
    ``salis/utils/__init__.py`` and ``salis/api/driver_portal/__init__.py``
    both define real public functions directly, not just re-exports) —
    '__init__' alone is a meaningless name to search for, so fall back to the
    parent directory's name.
    """
    base = os.path.splitext(os.path.basename(path))[0]
    if base == "__init__":
        return os.path.basename(os.path.dirname(path))
    return base


# The four must-test classes.

def _is_doctype_controller(path):
    """<module>/doctype/<slug>/<slug>.py — Frappe's own convention-loaded
    DocType controller path (same shape as
    test_duplicate_and_dead_code_guard.py's ``_is_convention_loaded``,
    narrowed here to just the doctype case). Requires a real ``.py`` file so
    a sibling ``<slug>.js`` client script (same basename-equals-parent shape)
    is never mistaken for the Python controller."""
    if not path.endswith(".py"):
        return False
    base = os.path.splitext(os.path.basename(path))[0]
    parent = os.path.basename(os.path.dirname(path))
    grandparent = os.path.basename(os.path.dirname(os.path.dirname(path)))
    return base == parent and grandparent == "doctype"


def _is_report_controller(path):
    """<module>/report/<slug>/<slug>.py — Frappe's own convention-loaded
    script-report path."""
    if not path.endswith(".py"):
        return False
    base = os.path.splitext(os.path.basename(path))[0]
    parent = os.path.basename(os.path.dirname(path))
    grandparent = os.path.basename(os.path.dirname(os.path.dirname(path)))
    return base == parent and grandparent == "report"


def _is_api_module(path):
    """Any file under a directory literally named 'api' ANYWHERE in its
    path — covers a nested package too (``salis/api/driver_portal/fuel.py``
    matches via its 'api' ancestor, not just direct children of api/)."""
    return "api" in _rel(path).split(os.sep)[:-1]


def _is_utils_module(path):
    """Any file under a directory literally named 'utils', or literally
    named utils.py. Covers a `utils/__init__.py` that IS the module (see
    _module_basename) as well as a plain `utils/some_helper.py`."""
    parts = _rel(path).split(os.sep)
    return os.path.basename(path) == "utils.py" or "utils" in parts[:-1]


def _count_code_lines(text):
    """Non-blank, non-comment source lines — a crude, easy-to-explain,
    deliberately IMPRECISE proxy for 'non-trivial' (goal: '>~10 lines').
    Pragmatic over exact: a long docstring can inflate this count, which only
    means an occasional simple-but-well-documented controller gets asked for
    a test it might not strictly need — a low-cost false positive (one extra
    baseline line), never a missed real gap."""
    return sum(1 for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("#"))


def _code_line_count(path):
    with open(path, encoding="utf-8") as fh:
        return _count_code_lines(fh.read())


def _public_top_level_functions(tree):
    return sorted(
        n.name
        for n in tree.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and not n.name.startswith("_")
    )


def _whitelisted_functions(tree):
    """Every function anywhere in the module (top-level or nested — a
    whitelisted endpoint can sit inside a class) carrying an
    ``@frappe.whitelist(...)`` / ``@whitelist(...)`` decorator."""
    names = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            target = dec.func if isinstance(dec, ast.Call) else dec
            is_whitelist = (
                isinstance(target, ast.Attribute) and target.attr == "whitelist"
            ) or (isinstance(target, ast.Name) and target.id == "whitelist")
            if is_whitelist:
                names.append(node.name)
                break
    return sorted(names)


def _has_execute(tree):
    return any(
        isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "execute"
        for n in tree.body
    )


def _doctype_json_name(path):
    """The DocType's declared human ``name`` from its sibling <slug>.json —
    the string Frappe/tests actually key on (frappe.get_doc({"doctype":
    ...}), frappe.new_doc(...)), never the Python module's dotted path."""
    d = os.path.dirname(path)
    json_path = os.path.join(d, os.path.basename(d) + ".json")
    if not os.path.exists(json_path):
        return None
    with open(json_path, encoding="utf-8") as fh:
        try:
            data = json.load(fh)
        except json.JSONDecodeError:
            return None
    return data.get("name") if isinstance(data, dict) else None


def _must_test_units():
    """{rel_path: (kind, [names])} for every production unit in one of the
    four must-test classes. Checked in a fixed order; in this codebase's
    layout a file matches at most one kind (a doctype controller never also
    sits under an api/ or utils/ dir)."""
    units = {}
    for path in _production_py_files():
        tree = _parse(path)
        if tree is None:
            continue
        rel = _rel(path)

        if _is_api_module(path):
            wl = _whitelisted_functions(tree)
            if wl:
                units[rel] = ("api", wl)
                continue

        if _is_doctype_controller(path) and _code_line_count(path) > 10:
            units[rel] = ("doctype", [])
            continue

        if _is_report_controller(path) and _has_execute(tree):
            units[rel] = ("report", [])
            continue

        if _is_utils_module(path):
            pub = _public_top_level_functions(tree)
            if pub:
                units[rel] = ("utils", pub)
                continue

    return units


# "Covered" — colocation, plus several independent reference signals.

def _test_reference_index():
    """One pass over every test_*.py file, building the lookup structures
    every ``_covered_by_*`` check needs. Computed ONCE per test run (not once
    per production file) — O(tests) not O(units x tests)."""
    dotted_refs = set()
    basename_dirs = {}
    text_blobs = []

    for tpath in _test_py_files():
        tree = _parse(tpath)
        if tree is not None:
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        dotted_refs.add(alias.name)
                elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                    dotted_refs.add(node.module)
                    for alias in node.names:
                        # [#a108d1] `from apex.x.y import pkg` — `pkg` may
                        # itself be the covered target, not just a re-exported
                        # name inside it (e.g. `from apex.apex_core.utils
                        # import portal_token_security`).
                        dotted_refs.add(f"{node.module}.{alias.name}")
        with open(tpath, encoding="utf-8") as fh:
            text = fh.read()
        for m in _DOTTED_RE.finditer(text):
            dotted_refs.add(m.group(0))
        text_blobs.append(text)
        base = os.path.splitext(os.path.basename(tpath))[0]
        basename_dirs.setdefault(base, set()).add(os.path.dirname(tpath))

    return {
        "dotted_refs": dotted_refs,
        "basename_dirs": basename_dirs,
        "all_text": "\n".join(text_blobs),
    }


def _covered_by_colocated_file(path, index):
    want = "test_" + _module_basename(path)
    return os.path.dirname(path) in index["basename_dirs"].get(want, ())


def _covered_by_dotted_reference(path, index):
    """A static `import`/`from ... import ...` of the module's dotted path,
    or a literal quoted-string mention of it, anywhere in a test file."""
    dotted = _file_dotted_path(path)
    return any(r == dotted or r.startswith(dotted + ".") for r in index["dotted_refs"])


def _covered_by_called_name(names, index):
    """A whitelisted/public function re-exported and called off its PARENT
    package instead of its own module (``salis/api/driver_portal/attendance
    .py``'s own docstring documents exactly this — see module docstring
    signal (d)) — the bare function name itself is called (``name(``)
    somewhere in a test, regardless of what precedes the dot."""
    for name in names:
        if re.search(r"\b" + re.escape(name) + r"\b\s*\(", index["all_text"]):
            return True
    return False


def _covered_by_doctype_name(path, index):
    """Frappe ORM tests key on the DocType's human NAME string
    (``frappe.get_doc({"doctype": "X", ...})``), never a Python import of the
    controller — the dominant real coverage signal for a "detached
    controller" (bare ``class X(Document): pass`` + module-level hooks)."""
    name = _doctype_json_name(path)
    if not name:
        return False
    return f'"{name}"' in index["all_text"] or f"'{name}'" in index["all_text"]


def _covered_by_report_basename_string(path, index):
    """A dynamic sweep test (`frappe.get_module(f"...{report_module}...")`
    driven by a `REPORTS = [...]` list constant) never contains the report's
    dotted path as text — only its bare basename, as one list element."""
    base = _module_basename(path)
    return f'"{base}"' in index["all_text"] or f"'{base}'" in index["all_text"]


def _is_covered(path, kind, names, index):
    if _covered_by_colocated_file(path, index):
        return True
    if _covered_by_dotted_reference(path, index):
        return True
    if kind == "doctype" and _covered_by_doctype_name(path, index):
        return True
    if kind in ("api", "utils") and _covered_by_called_name(names, index):
        return True
    if kind == "report" and _covered_by_report_basename_string(path, index):
        return True
    return False


def _uncovered_units():
    """{rel_path: kind} for every must-test unit that fails every covered-by
    signal above."""
    index = _test_reference_index()
    units = _must_test_units()
    return {
        rel: kind
        for rel, (kind, names) in units.items()
        if not _is_covered(os.path.join(APP_ROOT, rel), kind, names, index)
    }


# [#a108b1] Baseline frozen 2026-07-25, then fully drained by A-114 (2026-07-25):
# each of the original 25 units now carries a real colocated ``test_<name>.py``
# that exercises its behaviour, so every one is detected as covered by the
# signals above and the baseline is empty. The guard fails only when the
# uncovered set grows BEYOND this set (i.e. NEW untested code) — with an empty
# baseline that means the instant any new api/doctype/report/utils unit ships
# with no test anywhere in the tree.
_BASELINE = frozenset()


class TestMustTestClassification(unittest.TestCase):
    """Self-tests for the four must-test classifiers — pure path/AST logic,
    no file I/O beyond the synthetic snippets and a few known repo fixtures.
    """

    def test_scan_finds_production_files(self):
        self.assertTrue(_production_py_files(), "production .py scan found nothing — path broke")

    def test_doctype_controller_recognises_a_known_controller(self):
        # [#a108t1]
        known = os.path.join(APP_ROOT, "habitat", "doctype", "building", "building.py")
        self.assertTrue(os.path.exists(known), "fixture path drifted — update this test")
        self.assertTrue(_is_doctype_controller(known))
        self.assertFalse(_is_report_controller(known))

    def test_doctype_controller_rejects_sibling_files(self):
        # [#a108t2]
        d = os.path.join(APP_ROOT, "habitat", "doctype", "building")
        self.assertFalse(_is_doctype_controller(os.path.join(d, "building.js")))
        self.assertFalse(_is_doctype_controller(os.path.join(d, "building_dashboard.py")))

    def test_report_controller_recognises_a_known_report(self):
        known = os.path.join(
            APP_ROOT, "habitat", "report", "housing_cleaning_audit", "housing_cleaning_audit.py"
        )
        self.assertTrue(os.path.exists(known), "fixture path drifted — update this test")
        self.assertTrue(_is_report_controller(known))
        self.assertFalse(_is_doctype_controller(known))

    def test_api_module_matches_nested_package(self):
        # [#a108t3] salis/api/driver_portal/fuel.py — 'api' is an ANCESTOR,
        # not the immediate parent.
        p = os.path.join(APP_ROOT, "salis", "api", "driver_portal", "fuel.py")
        self.assertTrue(os.path.exists(p), "fixture path drifted — update this test")
        self.assertTrue(_is_api_module(p))

    def test_utils_module_matches_package_init(self):
        # [#a108t4] salis/utils/__init__.py IS the module in this codebase.
        p = os.path.join(APP_ROOT, "salis", "utils", "__init__.py")
        self.assertTrue(os.path.exists(p), "fixture path drifted — update this test")
        self.assertTrue(_is_utils_module(p))
        self.assertEqual(_module_basename(p), "utils")

    def test_module_basename_falls_back_to_parent_dir_for_init(self):
        p = os.path.join(APP_ROOT, "salis", "api", "driver_portal", "__init__.py")
        self.assertEqual(_module_basename(p), "driver_portal")
        self.assertEqual(_module_basename(os.path.join(APP_ROOT, "salis", "api", "masar.py")), "masar")

    def test_code_line_count_ignores_blank_and_comment_lines(self):
        # [#a108t5]
        src = "# Copyright\n\n\nimport frappe\n\n\nclass X:\n    pass\n"
        self.assertEqual(_count_code_lines(src), 3)  # import, class, pass

    def test_whitelisted_functions_detects_decorator_ignores_plain_def(self):
        # [#a108t6]
        tree = ast.parse(
            "import frappe\n\n"
            "@frappe.whitelist()\ndef submit_thing():\n    pass\n\n"
            "def _helper():\n    pass\n\n"
            "def plain():\n    pass\n"
        )
        self.assertEqual(_whitelisted_functions(tree), ["submit_thing"])

    def test_has_execute_true_only_for_module_level_execute(self):
        # [#a108t7]
        tree = ast.parse("def execute(filters=None):\n    return [], []\n")
        self.assertTrue(_has_execute(tree))
        tree2 = ast.parse("class Report:\n    def execute(self):\n        pass\n")
        self.assertFalse(_has_execute(tree2), "a nested method named execute is not a report entrypoint")

    def test_public_top_level_functions_excludes_private_and_nested(self):
        # [#a108t8]
        tree = ast.parse(
            "def get_thing():\n    pass\n\n"
            "def _private():\n    pass\n\n"
            "class C:\n    def method(self):\n        pass\n"
        )
        self.assertEqual(_public_top_level_functions(tree), ["get_thing"])

    def test_doctype_json_name_reads_the_sibling_json(self):
        p = os.path.join(APP_ROOT, "habitat", "doctype", "building", "building.py")
        self.assertEqual(_doctype_json_name(p), "Building")


class TestCoverageSignals(unittest.TestCase):
    """Self-tests for each independent 'covered' signal, using small
    synthetic indexes — no repo scan needed to prove the logic itself."""

    def _fake_path(self, *parts):
        """A path rooted at the REAL REPO_ROOT (so _file_dotted_path resolves
        cleanly) but a made-up filename — fine, since none of these
        detectors touch the filesystem except _covered_by_doctype_name."""
        return os.path.join(REPO_ROOT, "apex", *parts)

    def test_covered_by_colocated_file(self):
        p = self._fake_path("salis", "widget", "widget.py")
        index = {
            "dotted_refs": set(),
            "basename_dirs": {"test_widget": {os.path.dirname(p)}},
            "all_text": "",
        }
        self.assertTrue(_covered_by_colocated_file(p, index))
        index["basename_dirs"] = {"test_widget": {"/some/other/dir"}}
        self.assertFalse(_covered_by_colocated_file(p, index))

    def test_covered_by_dotted_reference_exact_and_suffix(self):
        p = self._fake_path("salis", "api", "widget.py")
        dotted = _file_dotted_path(p)
        self.assertEqual(dotted, "apex.salis.api.widget")
        index = {"dotted_refs": {dotted}, "basename_dirs": {}, "all_text": ""}
        self.assertTrue(_covered_by_dotted_reference(p, index))
        index2 = {"dotted_refs": {dotted + ".submit_widget"}, "basename_dirs": {}, "all_text": ""}
        self.assertTrue(_covered_by_dotted_reference(p, index2))
        index3 = {"dotted_refs": {"apex.salis.api.widget_extra"}, "basename_dirs": {}, "all_text": ""}
        self.assertFalse(_covered_by_dotted_reference(p, index3))

    def test_covered_by_called_name(self):
        index = {"dotted_refs": set(), "basename_dirs": {}, "all_text": "x = submit_fuel_request(doc)\n"}
        self.assertTrue(_covered_by_called_name(["submit_fuel_request"], index))
        index2 = {"dotted_refs": set(), "basename_dirs": {}, "all_text": "# submit_fuel_request is great\n"}
        self.assertFalse(
            _covered_by_called_name(["submit_fuel_request"], index2),
            "a bare mention with no call parens must not count",
        )

    def test_covered_by_called_name_when_called_off_parent_package(self):
        # [#a108t9] the real driver_portal/attendance.py shape: the module's
        # own name ("attendance") never appears anywhere in the test, only
        # the re-exported function called off the parent package.
        index = {
            "dotted_refs": set(),
            "basename_dirs": {},
            "all_text": "res = driver_portal.my_attendance()\n",
        }
        self.assertTrue(_covered_by_called_name(["my_attendance"], index))

    def test_covered_by_doctype_name_reads_real_json(self):
        p = os.path.join(APP_ROOT, "habitat", "doctype", "building", "building.py")
        index = {"dotted_refs": set(), "basename_dirs": {}, "all_text": 'x = "Building"\n'}
        self.assertTrue(_covered_by_doctype_name(p, index))
        index2 = {"dotted_refs": set(), "basename_dirs": {}, "all_text": "no mention here\n"}
        self.assertFalse(_covered_by_doctype_name(p, index2))

    def test_covered_by_report_basename_string(self):
        p = self._fake_path("habitat", "report", "widget_report", "widget_report.py")
        index = {"dotted_refs": set(), "basename_dirs": {}, "all_text": 'REPORTS = ["widget_report"]\n'}
        self.assertTrue(_covered_by_report_basename_string(p, index))
        index2 = {"dotted_refs": set(), "basename_dirs": {}, "all_text": "REPORTS = []\n"}
        self.assertFalse(_covered_by_report_basename_string(p, index2))


class TestUnitTestCoverageGuard(unittest.TestCase):
    def test_scan_finds_must_test_units_of_all_four_kinds(self):
        units = _must_test_units()
        self.assertTrue(units, "must-test scan found nothing — path broke")
        kinds = {kind for kind, _names in units.values()}
        self.assertEqual(
            kinds, {"api", "doctype", "report", "utils"}, "one of the four kinds vanished"
        )

    def test_no_new_uncovered_unit(self):
        """No production unit may ship with zero test presence beyond the
        frozen baseline.

        A failure means a NEW api/doctype/report/utils module (see module
        docstring for the exact four classes) has no test anywhere in the
        tree under any of the five covered-by signals. Fix by either:
          1. adding/extending a test that imports the module (or, for a
             DocType, that creates one via ``frappe.get_doc({"doctype": ...})``),
             ideally colocated as ``test_<name>.py`` next to the module
             (A-108's target end-state), or
          2. if this really is pre-existing debt rather than your change,
             add the path to ``_BASELINE`` in this file with a one-line
             reason — but prefer writing the test.
        """
        uncovered = _uncovered_units()
        new = set(uncovered) - _BASELINE
        self.assertEqual(
            new,
            set(),
            "New production unit(s) with no test anywhere in the tree:\n"
            + "\n".join(f"  [{uncovered[rel]}] {rel}" for rel in sorted(new)),
        )

    def test_baseline_paths_still_exist(self):
        """Every _BASELINE entry must still be a real file — catches a stale
        baseline left behind by a rename/delete (mirrors
        test_sql_interpolation_guard.py's test_allowlist_entries_still_exist)."""
        missing = sorted(
            p for p in _BASELINE if not os.path.exists(os.path.join(APP_ROOT, p))
        )
        self.assertEqual(
            missing,
            [],
            f"_BASELINE references path(s) that no longer exist — update the "
            f"baseline (the file was likely renamed or removed): {missing}",
        )


if __name__ == "__main__":
    unittest.main()
