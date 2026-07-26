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
this guard must recognise coverage in either home) PLUS the plain-named shared
helpers under ``tests/`` (``source_tree.test_support_files``). A-176 proved why
the second half matters: promoting a duplicated Goods Receipt fixture out of two
test modules into factories.py moved the only ``"Goods Receipt"`` mention out of
the ``test_*.py`` universe, and the guard scored a de-duplication as a lost test.

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

Standalone-runnability guard (A-192)
------------------------------------
A test module that documents a plain ``python3 -m unittest ...`` invocation is
making a FALSIFIABLE claim: it imports and runs with no bench and no live site.
That claim rots silently. ``apex_core/utils/test_guarded_index_dedupe.py`` made
it, then a refactor gave the module under test a ``frappe._`` and a
``frappe.model.document`` import its fake-frappe fallback did not stub — the
documented command gave ``FAILED (errors=4)`` while CI stayed green, because
``bench run-tests`` has the REAL frappe in ``sys.modules`` and never enters the
fallback branch at all. Nothing detects that: the file was fixed, the CLASS was
not. ``TestDeclaredStandaloneModulesStayRunnable`` below executes each claim.

Shape, and why this one (cost matters — this module runs in CI's deliberately
fast ``python3 -m unittest`` lane, not only under bench):
  * A FULL RUN of the module's tests, not an import. Import-only was measured
    and REJECTED: it is 15x cheaper (0.55s vs 8.2s across 21 modules) but it
    misses the very defect A-192 is named for. ``test_guarded_index_dedupe``'s
    regression was not a module-scope ImportError — its own comment records that
    ``execute()`` drags in ``housing_assignment``, i.e. the uncovered
    ``frappe.model.document`` import fires INSIDE a test method, which is why the
    card observed ``FAILED (errors=4)`` rather than a load error. Import-only
    goes green on that break. Measured here: it catches 1 of the 2 real rots in
    this tree, missing ``test_habitat_permission_hooks``, whose
    ``from apex.habitat.permissions import ...`` also sits inside a test body.
    Running the documented command is the only honest check of the documented
    command.
  * ONE SUBPROCESS PER MODULE, the cost that cannot be optimised away: these
    modules install a FAKE frappe into ``sys.modules`` at import time, so sharing
    one interpreter lets module A's stub satisfy module B and every claim after
    the first passes on borrowed state. Run in PARALLEL (threads around
    subprocesses — the work is entirely out-of-process), so the wall cost is the
    slowest module, not the sum.
  * THIS module is excluded from its own sweep. Probing itself would re-enter
    this sweep one level down, and its standalone claim is already proven
    directly by the CI step that runs ``python3 -m unittest
    apex.tests.test_unit_test_coverage_guard`` in a frappe-free lane.
The probe
~~~~~~~~~
frappe is blocked by a ``sys.meta_path`` finder, NOT by stripping ``sys.path``
(which would take ``apex`` out with it). This is the load-bearing part: the same
module also runs under ``bench run-tests``, where frappe IS installed, so a probe
that merely inherited the environment would import the real frappe, skip every
fallback branch and prove nothing — the exact false green A-192 is about.
``sys.modules`` is consulted BEFORE ``meta_path``, so a module's own fake-frappe
fallback still works once it installs its stub; only the real frappe is
unreachable. The finder raises ``ModuleNotFoundError``, which is what a genuinely
absent module raises, so a module guarding with ``except ModuleNotFoundError``
behaves exactly as it would off-bench. ``loadTestsFromName`` turns a load failure
into a ``_FailedTest`` instead of raising, so an import error and a test error
both land in ``wasSuccessful()``.

Rot baseline — EMPTY since A-205 (2026-07-26)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The two modules A-192 found now pass the command they advertise. Each grew the
fake-frappe fallback its own import chain needs — ``www/test_masar_supervisor_map
_tiles.py`` stubs ``frappe.sessions`` / ``frappe.utils`` / ``frappe.model.document``,
``habitat/test_habitat_permission_hooks.py`` stubs a bare ``frappe`` module. Stubbing
was the honest fix for BOTH rather than deleting the claim, because in neither case
does the unit under test call frappe at all: ``map_tile_override`` is pure string
validation over a plain dict, and the habitat guards only assert wiring and
importability. Each file's own comment records why its stub cannot fake a pass.
With the baseline empty, any module whose documented command breaks reds at once.

Fast-lane exemption (A-206) — ONE module, in ONE lane
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
This sweep made CI's frappe-free guards step go from ~0.7s to 5.0s (measured
5.01 / 5.03 / 5.09s), and 3.68s of that was a SINGLE probe:
``apex.tests.test_duplicate_and_dead_code_guard``. The subprocess is not the cost —
that module takes 3.55s run directly, because it AST-parses the whole tree several
times. Every other claim in the sweep costs 0.80s or less. So the fast lane sets
``APEX_SKIP_SLOW_STANDALONE_PROBES=1`` (inline on that one ``run:`` line, nowhere
else) and the sweep drops that one module: 2.08 / 2.10 / 2.11s measured after.

2.1s, not 0.7s, and the workflow comment now says so. The old ~0.7s is unrecoverable
and was never going to come back by exempting one module: ~0.7s is what the two
ratchet SCANS cost on their own, and the 19 remaining standalone runs cost ~1.1s wall
however they are scheduled (measured at 8 / 16 / 24 workers: 1.12 / 1.31 / 1.27s —
already past this machine's useful parallelism, so more threads make it worse). That
~1.3s is the price of the only check that can see a broken documented command at all,
since ``bench run-tests`` has the real frappe loaded and never enters a fallback
branch. It is paid ahead of a ~25min bench install, and it is worth paying.

What the exemption costs, stated plainly: in the FAST lane that module's standalone
claim is not executed, so a rot in it is not caught in ~1.3s. It is NOT unverified —
this whole module also runs under ``bench run-tests --app apex``, which sets no such
variable and therefore sweeps all 20 claims, and a plain local
``python3 -m unittest apex.tests.test_unit_test_coverage_guard`` does too. The cost
is a DELAY on exactly one claim (fast lane -> the ~25min bench job), not a hole.
Two ratchets keep it that narrow: ``test_the_fast_lane_exemption_stays_one_named
_live_claim`` refuses a second entry or a stale one, and
``test_only_the_fast_guards_step_sets_the_skip_flag`` refuses to let the variable
escape that single command into a job- or workflow-level ``env:`` block, which is
the one edit that WOULD blind the bench lane too.

Run standalone (from the repo root, so ``apex.tests.source_tree`` resolves):
  python3 -m unittest apex.tests.test_unit_test_coverage_guard -v
"""

import ast
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache

from apex.tests.source_tree import (
    APP_ROOT,
    REPO_ROOT,
    file_dotted_path as _file_dotted_path,
    parse as _parse,
    production_py_files as _production_py_files,
    rel as _rel,
    test_py_files as _test_py_files,
    test_support_files as _test_support_files,
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

    for tpath in _test_py_files() + _test_support_files():
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


# Standalone-runnability guard (A-192) — see the module docstring for the shape
# decision and its measured cost.

# [#a192m1] The marker is the DOCUMENTED COMMAND, not the words "Run standalone".
# Several modules use that heading for a `bench --site <site> run-tests` command,
# which explicitly REQUIRES a live site and claims nothing about plain python.
# Matching the heading would fail 3 modules for a promise they never made.
_STANDALONE_CMD_RE = re.compile(r"python3?\s+-m\s+unittest")

# [#a192p1] Runs in the probe subprocess; see "The probe" in the module docstring.
_NO_FRAPPE_PROBE = """
import sys
import unittest


class _NoFrappe:
    def find_spec(self, name, path=None, target=None):
        if name == "frappe" or name.startswith("frappe."):
            raise ModuleNotFoundError("No module named 'frappe'", name=name)
        return None


sys.meta_path.insert(0, _NoFrappe())
suite = unittest.TestLoader().loadTestsFromName(sys.argv[1])
result = unittest.TextTestRunner(verbosity=0).run(suite)
sys.exit(0 if result.wasSuccessful() else 1)
"""

# This module's own dotted path — excluded from the sweep it runs (see docstring).
# Derived from __file__, not __name__, which is "__main__" under direct execution.
_SELF_DOTTED = _file_dotted_path(os.path.abspath(__file__))

# [#a192b1] The rot this guard FOUND is FIXED, not blessed: A-205 gave both modules the
# fake-frappe fallback their import chains need, so the baseline is empty and every
# declared claim is now enforced. See "Rot baseline" in the module docstring.
_STANDALONE_ROT_BASELINE = frozenset()

# [#a206s1] A-206: the one probe that cost more than the entire rest of the fast lane —
# 3.68s of a 5.01s step, and 3.55s run directly, so this is the module's own tree-scan
# cost, not subprocess overhead. Dropped from the sweep ONLY when the fast lane asks;
# `bench run-tests` and a plain local run still execute it. See "Fast-lane exemption"
# in the module docstring for what that delay costs and why it is not a hole.
_SLOW_STANDALONE_MODULES = frozenset({"apex.tests.test_duplicate_and_dead_code_guard"})

# Set inline on ONE `run:` line in .github/workflows/test.yml and nowhere else — a
# job- or workflow-level `env:` block would reach the bench job too and turn the
# delay into a real hole. test_only_the_fast_guards_step_sets_the_skip_flag refuses it.
_SKIP_SLOW_PROBES_ENV = "APEX_SKIP_SLOW_STANDALONE_PROBES"
_SKIP_SLOW_PROBES = os.environ.get(_SKIP_SLOW_PROBES_ENV) == "1"


@lru_cache(maxsize=1)
def _standalone_declared_modules():
    """{dotted path: rel path} for each test module documenting a plain
    ``python3 -m unittest`` invocation, excluding this module itself.

    Cached: it AST-parses every test file (0.17s), and three tests in this class ask
    for it, so an uncached call was 0.34s of pure repeat in a lane whose whole point
    is being fast. Callers only READ the mapping — never mutate the shared dict.
    """
    found = {}
    for path in _test_py_files():
        tree = _parse(path)
        if tree is None:
            continue
        if _STANDALONE_CMD_RE.search(ast.get_docstring(tree) or ""):
            dotted = _file_dotted_path(path)
            if dotted != _SELF_DOTTED:
                found[dotted] = _rel(path)
    return found


def _probe_standalone_run(dotted, extra_path=None):
    """Run ``dotted``'s tests in a fresh interpreter that cannot import frappe.

    REPO_ROOT leads PYTHONPATH so the probe always exercises THIS tree, never an
    ``apex`` installed elsewhere (an editable bench install otherwise wins)."""
    pythonpath = [REPO_ROOT] + list(extra_path or [])
    return subprocess.run(
        [sys.executable, "-c", _NO_FRAPPE_PROBE, dotted],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": os.pathsep.join(pythonpath)},
    )


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

    def test_index_universe_includes_the_shared_test_helpers(self):
        # [#a176t1] A fixture promoted into factories.py is still test presence —
        # if this universe narrows back to test_*.py, de-duplicating reads as a
        # lost test and the guard punishes the cleanup it should reward.
        support = {os.path.basename(p) for p in _test_support_files()}
        self.assertIn("factories.py", support)
        self.assertIn("_helpers.py", support)
        self.assertNotIn("__init__.py", support)
        self.assertFalse(any(b.startswith("test_") for b in support))

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


class TestDeclaredStandaloneModulesStayRunnable(unittest.TestCase):
    """A-192: execute every self-declared standalone claim, don't just read it."""

    def test_probe_cannot_reach_a_genuinely_importable_frappe(self):
        """Guard-of-the-guard: prove the blocker BLOCKS, not that frappe is absent.

        Without this, the whole guard silently degrades to a no-op on any machine
        that has no frappe installed — every probe would pass for the wrong
        reason, and on CI (where frappe IS installed) it would pass for the other
        wrong reason. Plant a real, importable frappe and prove both directions.
        """
        with tempfile.TemporaryDirectory() as tmp:
            pkg = os.path.join(tmp, "frappe")
            os.makedirs(pkg)
            with open(os.path.join(pkg, "__init__.py"), "w", encoding="utf-8") as fh:
                fh.write("MARKER = 'planted frappe'\n")

            control = subprocess.run(
                [sys.executable, "-c", "import frappe; print(frappe.MARKER)"],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                env={**os.environ, "PYTHONPATH": os.pathsep.join([REPO_ROOT, tmp])},
            )
            self.assertEqual(
                control.returncode, 0, "planted frappe is not importable — test setup broke"
            )
            self.assertIn("planted frappe", control.stdout)

            blocked = _probe_standalone_run("frappe", extra_path=[tmp])
            self.assertNotEqual(
                blocked.returncode,
                0,
                "the meta_path blocker did NOT block an importable frappe — every "
                "standalone probe below is therefore meaningless",
            )
            self.assertIn("No module named 'frappe'", blocked.stderr)

    def test_declared_standalone_modules_actually_run_without_frappe(self):
        """Each module documenting `python3 -m unittest` must actually PASS with
        no frappe available.

        A failure means the documented command is a lie: the module, or something
        it reaches, grew a frappe dependency its fake-frappe fallback does not
        cover — and `bench run-tests` cannot see it, because with the real frappe
        in sys.modules the fallback branch is never taken. Fix by stubbing what is
        now imported, or by deleting the standalone claim if the module genuinely
        needs a site.
        """
        declared = _standalone_declared_modules()
        self.assertGreater(
            len(declared), 10, "standalone-claim scan found implausibly few modules"
        )

        # [#a206s2] The fast lane drops the one slow probe; every other caller
        # (bench run-tests, a plain local run) sweeps the full set.
        targets = sorted(
            set(declared) - _SLOW_STANDALONE_MODULES if _SKIP_SLOW_PROBES else declared
        )

        broken = {}
        with ThreadPoolExecutor(max_workers=8) as pool:
            for dotted, result in zip(targets, pool.map(_probe_standalone_run, targets)):
                if result.returncode != 0:
                    tail = result.stderr.strip().splitlines()
                    broken[dotted] = tail[-1] if tail else f"exit {result.returncode}"

        regressed = sorted(set(broken) - _STANDALONE_ROT_BASELINE)
        self.assertEqual(
            regressed,
            [],
            "Module(s) documenting a standalone `python3 -m unittest` run that no "
            "longer pass without frappe — the documented command is broken while "
            "bench run-tests stays green (it never takes the fallback branch):\n"
            + "\n".join(f"  {d}  ({declared[d]})\n      {broken[d]}" for d in regressed),
        )

    def test_the_fast_lane_exemption_stays_one_named_live_claim(self):
        """A-206: the exemption may not grow, and may not cover a dead claim.

        Its whole defence is that it costs the fast lane exactly ONE delayed claim.
        A second entry, or an entry whose module stopped declaring a standalone run
        (renamed, deleted, claim dropped), silently widens that cost — so both are
        refused here rather than discovered later.
        """
        self.assertEqual(
            len(_SLOW_STANDALONE_MODULES),
            1,
            "the fast-lane exemption grew beyond the one measured module — re-measure "
            "the step and justify each addition in the module docstring, or drop it",
        )
        declared = _standalone_declared_modules()
        stale = sorted(_SLOW_STANDALONE_MODULES - set(declared))
        self.assertEqual(
            stale,
            [],
            "fast-lane exemption names module(s) that declare no standalone run at "
            f"all — prune them, they exempt nothing: {stale}",
        )

    def test_only_the_fast_guards_step_sets_the_skip_flag(self):
        """A-206: the skip flag must stay welded to ONE command.

        Promoting it to a job- or workflow-level ``env:`` block would reach the bench
        job as well, and the exemption would stop being a delay and become the hole
        the fast lane's whole defence says it is not. One occurrence, inline on the
        one ``run:`` line that invokes this guard.
        """
        workflow = os.path.join(REPO_ROOT, ".github", "workflows", "test.yml")
        self.assertTrue(os.path.exists(workflow), f"{workflow} moved — update this test")
        with open(workflow, encoding="utf-8") as fh:
            text = fh.read()
        hits = [ln for ln in text.splitlines() if _SKIP_SLOW_PROBES_ENV in ln]
        self.assertEqual(
            len(hits),
            1,
            f"{_SKIP_SLOW_PROBES_ENV} must appear exactly once in test.yml, inline on "
            f"the fast guards step; found {len(hits)} occurrence(s):\n"
            + "\n".join(hits),
        )
        self.assertRegex(
            hits[0],
            r"run:\s*" + re.escape(_SKIP_SLOW_PROBES_ENV) + r"=1 python3 -m unittest ",
            "the skip flag must be set inline on the guards step's own `run:` command, "
            "never in an `env:` block that would also reach the bench job",
        )

    def test_rot_baseline_is_neither_stale_nor_silently_fixed(self):
        """The rot baseline may only shrink, and only for a real reason."""
        declared = _standalone_declared_modules()
        unknown = sorted(_STANDALONE_ROT_BASELINE - set(declared))
        self.assertEqual(
            unknown,
            [],
            "Rot-baseline entr(ies) no longer declare a standalone run at all — the "
            "claim was dropped or the module moved. Prune them:\n"
            + "\n".join(f"  {d}" for d in unknown),
        )
        still_broken = {
            d for d in _STANDALONE_ROT_BASELINE
            if _probe_standalone_run(d).returncode != 0
        }
        fixed = sorted(_STANDALONE_ROT_BASELINE - still_broken)
        self.assertEqual(
            fixed,
            [],
            "Rot-baseline entr(ies) now import cleanly — prune them so the "
            "baseline cannot quietly re-absorb a future regression:\n"
            + "\n".join(f"  {d}" for d in fixed),
        )


if __name__ == "__main__":
    unittest.main()
