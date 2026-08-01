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

The DOCUMENTED target, not just the file's location (A-213)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The docstring used to be only a TRIGGER: match the command, then probe a dotted
path computed from the FILE PATH, never reading the string the docstring actually
prints. So a module could advertise ``tests.test_x`` — which resolves from
nowhere, this repo has no top-level ``tests/`` package — and the probe went green
while the documented line failed for the human who copied it. Seven docstrings
really did carry that shape; they were found and fixed BY HAND, by eye, not by
the guard whose entire purpose is that class.

``_STANDALONE_CMD_RE`` now CAPTURES the target, and
``test_documented_standalone_command_names_its_own_module`` asserts it names the
module it sits in — exactly, or as a ``Class[.method]`` selector beneath it,
since documenting one test method is a legitimate narrowing rather than a wrong
path. That check covers THIS module too: self-exclusion exists because probing
itself would re-enter the sweep one level down, which is a reason about running a
subprocess, not about comparing two strings.

What the pattern must TOLERATE — a guard that reds on a legitimate spelling of
the right command gets worked around, not obeyed. Verified against all 25
declarations in this tree, and the matched SET is identical to the old
trigger-only pattern, because every addition is optional:
  * ``python`` or ``python3``, and any run of whitespace between tokens;
  * the command WRAPPED across two lines — this module's own docstring wraps one,
    so the whitespace before the target has to match a newline;
  * flags on EITHER side of the target: a trailing ``-v`` (all 24 sibling
    declarations end that way), ``--failfast``, a ``-k`` filter. Value-taking
    flags are consumed together WITH their value, so a dotted ``-k`` selector
    sitting before the target is never mistaken for the target itself;
  * a target wrapped in RST double-backticks, or ending a sentence — ``\\w`` stops
    at the backtick and the dotted tail cannot eat a trailing full stop;
  * a PROSE mention carrying no target at all — the ``...`` placeholder above and
    the bare "fast lane" phrase further up are both in THIS docstring, so the
    target group is optional and such a match documents nothing to check.
The one thing it deliberately does not read: a target must contain a DOT. A
dotless token after the command is far likelier to be an English word than a
module path, and every real target in this app is ``apex.<...>``. The cost is
that a path-form target (``apex/tests/<name>.py``) is not captured — which reds
as "documents no resolvable target" rather than passing silently, so it is a loud
gap, not a hole.

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

The old ~0.7s is unrecoverable and was never going to come back by exempting one
module: ~0.7s is what the two ratchet SCANS cost on their own, and the remaining
standalone runs are the rest of the bill.

RE-MEASURED 2026-07-26 (A-215), because the claim count grew from 20 to 24 and a
timing welded to a different workload misattributes its own measurement. The 23
runs the fast lane still sweeps cost 1.51 / 1.45 / 1.46s at 8 / 16 / 24 workers
(best of three at each width); all 24, including the exempt module, cost 4.23s at
8 workers. So ~1.5s, up from the ~1.1s that 19 runs cost — and the old "more
threads make it worse" no longer holds: past 8 workers the wall is flat, a shade
better, not worse. CAVEAT, since it bit the previous measurement too: other agents
were building on this machine throughout (load average 1.4 rising to 2.1). These
are CONTENDED numbers, an upper bound rather than the quiet-machine figure — the
whole step measured 2.40 / 2.43 / 2.44s at load 1.7 and 2.60 / 2.61 / 2.61s at
load 2.5, against the 2.08 / 2.11s recorded on a quiet machine for a smaller
sweep. That spread is CONTENTION, not regression: the A-231 class added below
costs this lane 0.03s measured on its own, interpreter start included, because it
skips without a site.

That ~1.5s is the price of the only check that can see a broken documented command
at all, since ``bench run-tests`` has the real frappe loaded and never enters a
fallback branch. It is paid ahead of a ~25min bench install, and it is worth paying.

What the exemption costs, stated plainly: in the FAST lane that module's standalone
claim is not executed, so a rot in it is not caught in ~1.5s. It is NOT unverified —
this whole module also runs under ``bench run-tests --app apex``, which sets no such
variable and therefore sweeps all 24 claims, and a plain local
``python3 -m unittest apex.tests.test_unit_test_coverage_guard`` does too. The cost
is a DELAY on exactly one claim (fast lane -> the ~25min bench job), not a hole.
Two ratchets keep it that narrow: ``test_the_fast_lane_exemption_stays_one_named
_live_claim`` refuses a second entry or a stale one, and
``test_only_the_fast_guards_step_sets_the_skip_flag`` refuses to let the variable
escape that single command into a job- or workflow-level ``env:`` block, which is
the one edit that WOULD blind the bench lane too.

Process-global leak guard (A-231)
---------------------------------
A test that stubs a frappe PROCESS GLOBAL and never puts it back aborts every test
that runs after it in the same interpreter — and each victim still passes IN
ISOLATION, which is why this class of defect clears review. It happened here:
a report test left ``frappe.local.db`` as a ``types.SimpleNamespace``, and
``bench run-tests --app apex`` went from 2620 passing to ``259 errors`` with an
early abort, every victim dying in ``FrappeTestCase.setUpClass`` on
``AttributeError: 'types.SimpleNamespace' object has no attribute 'commit'``.
setUpClass calls ``frappe.db.commit()``, and ``frappe.db`` is a proxy onto
``frappe.local``, so one unrestored attribute reaches every later test class.

The shape, and why nothing weaker will do: run the module in its OWN site-connected
interpreter, diff ``frappe.local`` against a snapshot taken before it ran, then run
a real ``FrappeTestCase`` canary IN THE SAME PROCESS. Neither half is redundant —
the diff names WHAT was stranded but only guesses at the damage, and the canary
proves the damage but cannot see a stub that merely looks harmless.

What counts as left behind
~~~~~~~~~~~~~~~~~~~~~~~~~~
  * an attribute that existed before and now holds a DIFFERENT TYPE — the incident
    exactly (``MariaDBDatabase`` replaced by ``SimpleNamespace``);
  * an attribute that existed before and is now deleted, or is now None;
  * an attribute that did NOT exist before and is now None. ``frappe.local`` is a
    werkzeug ``Local``: reading an unset name raises AttributeError and iterating
    it does not list that name at all, so ABSENCE IS A VALUE and None is a
    different state. A harness that snapshots with ``getattr(frappe.local, name,
    None)`` and restores by ``setattr`` silently converts unset into None;
  * an attribute that did not exist before and holds an object whose type the app
    or ``unittest.mock`` defines — a stub the test built, parked on a framework
    global;
  * a ``sys.modules["frappe*"]`` entry swapped for another object, or removed.
Deliberately NOT flagged: a NEW attribute holding a stdlib or third-party object.
Frappe fills its own locals lazily, so a first run legitimately adds
``request_cache`` (a ``collections.defaultdict``), ``jloader`` (a
``jinja2.ChoiceLoader``), ``_link_count``, ``system_settings``; a draft that
flagged every non-frappe type reported 13 of 18 clean modules as leaking.

Population, and its boundary
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
21 of 370 test modules when this was measured (2026-07-26), selected statically:
those that assign, ``setattr`` or ``delattr`` under ``frappe.local``, or swap a
``sys.modules["frappe*"]`` entry. Probing them all would re-run the whole suite in
subprocesses, and the population grows on its own — three modules joined it while
this guard was being written. A grep would not do the selecting either: the file
that caused the incident now writes through
``setattr(frappe.local, name, value)`` and matches no ``frappe.local.x =`` text at
all, so the scan is an AST walk over the assignment TARGET. The boundary stated
plainly — a bare ``frappe.<attr> = stub`` monkeypatch is not in this population,
and neither is a module that leaks only through a helper in another file.

Serial, and why (measured 2026-07-26 against a live ``test`` site)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
21 probes serially: 78.2s wall. The probe FLOOR is ~0.2s (frappe import, init,
connect, canary), so that number is the modules' own test time, not overhead — the
two heaviest account for 61s of it. At 8 workers the same sweep is 59.3s and WRONG:
21 interpreters against one site DB made ``test_boarding_scan`` load ZERO tests, so
its clean verdict means nothing. Reproduced twice, on two different populations,
and an earlier 8-worker run flipped four more modules to failing. 19s does not buy
that. Hence serial, plus an assertion that every probe actually RAN tests, since a
probe that runs nothing passes for the wrong reason.

Lane: this needs a live site, so the frappe-free fast lane SKIPS it and pays only a
failed ``import frappe`` — measured, the whole class plus its scanner self-tests
cost 0.03s there including interpreter start, and the population scan is never
called. It runs under ``bench run-tests``, where this module went from 5.02s to
86.07s against the live ``test`` site (39 tests, contended). That +81s sits inside
a ~25min job, which is where a guard against a whole-suite abort belongs.

Why a zero-test probe is RETRIED (A-253, root cause measured 2026-07-26)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The zero-test assertion above fired in 2 of 5 consecutive runs, each time naming a
DIFFERENT innocent module — ``test_permission_scope_shared`` once,
``test_boarding_scan`` twice — with three clean runs between. Two causes were
possible and the fix differs completely between them, so it was measured, not
guessed. It is NOT the guard's scheduling: this sweep is serial (the dict
comprehension below), and the ThreadPoolExecutor in this file belongs to the
frappe-free standalone sweep, which cannot emit this message at all. It is the
SHARED SITE. Reproduced by running 8 probes of ``test_boarding_scan`` at once
against the live ``test`` site: 7 of 8 returned exit code 0 with ``testsRun == 0``,
each having died in ``setUpClass`` on
``QueryDeadlockError: (1020, "Record has changed since last read in table 'tabseries'")``
— the naming-series row every autonamed fixture takes.

Two separate defects made that unreadable:
  * ``testsRun`` counts tests that STARTED. A ``setUpClass`` that raises is recorded
    against a class-level error holder and never increments it, so the probe exits
    0 reporting zero tests — indistinguishable, to the old code, from a module with
    no tests. The probe now also returns ``problems``, the target's own errors and
    failures, so the message carries the deadlock instead of an empty line.
  * A transient serialization conflict is retryable by definition; a single verdict
    from it is not. ``_probe_until_tests_run`` re-probes a zero-test return once in
    a FRESH interpreter with a fresh connection, and a module is named only when
    the retry also runs nothing. From the observed rate — one failing probe per 2.5
    runs over 21 probes, so p ≈ 0.019 each — one retry moves a run's odds from
    ~40% to well under 1%, which is why the second retry is not worth the delay it
    would add before a genuinely testless module is named.
The retry costs NOTHING on a healthy run: it fires only after a zero, and a
successful probe is returned on its first attempt (asserted below). So the lane
recommendation is unchanged — still serial, still bench-lane only, still skipped in
the frappe-free lane. Worst case is one extra probe for one module.

What this deliberately does NOT do is hide the deadlock: a retried-away conflict is
a property of a site shared with the parent test run and with whatever else is
connected, not of the module, so it is not this guard's finding to report. What
WOULD be a hole is a retry that swallows a real empty module, and that is closed by
a live plant that loads cleanly and defines no test.

Leak baseline — EMPTY since A-236 (2026-07-26)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The one entry this detector found on its first full sweep is fixed, not blessed:
``apex_core/utils/test_portal_token_throttle.py`` snapshotted with
``getattr(frappe.local, name, None)`` and restored by ``setattr``, so ``request`` —
UNSET before that module ran — was left as None afterwards. Harmless in itself,
because frappe reads it with a defaulted getattr, so the canary passed and only the
diff could see it; but it is precisely the absent-attribute shape the incident's own
fix had to solve. That module now snapshots against an ``_ABSENT`` sentinel and
``delattr``s an originally-unset name instead of writing None over it, through ONE
shared helper both its test classes use. With the baseline empty, any module that
strands a global reds at once, and the two assertions below stay live: a baseline
entry that stops leaking must be pruned, and one that stops writing globals at all
must be pruned too — so a drained entry can never be faked by deleting the stubbing.

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
from unittest import mock

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
#
# [#a213m1] It also CAPTURES the target — reading only the trigger is how a wrong
# documented path stayed green. Tolerances: "The DOCUMENTED target" in the docstring.
_STANDALONE_CMD_RE = re.compile(
    r"python3?\s+-m\s+unittest"
    # flags before the target; the value-taking ones swallow their value too
    r"(?:\s+(?:--pattern|--start-directory|--top-level-directory|-k|-p|-s|-t)\s+\S+"
    r"|\s+-{1,2}[A-Za-z][\w-]*)*"
    r"(?:\s+(?P<target>[A-Za-z_]\w*(?:\.\w+)+))?"
)


def _target_names_module(target, dotted):
    """Does the documented target actually run THIS module's tests?

    Exact match, or a ``Class``/``Class.method`` selector BENEATH it
    (``apex.tests.test_x.TestY.test_z``) — ``loadTestsFromName`` resolves those to
    this same file, so documenting one is a deliberate narrowing, not a wrong
    path. A PARENT package is refused: ``loadTestsFromName("apex.tests")``
    collects nothing from a plain package, so it would be a broken command rather
    than a broader one. Same exact-or-descendant rule as
    ``_covered_by_dotted_reference`` above, for the same reason.
    """
    return target == dotted or target.startswith(dotted + ".")


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
def _standalone_declarations():
    """``((rel, dotted, documented_targets), ...)`` for every test module whose
    MODULE docstring documents a plain ``python3 -m unittest`` run — this module
    INCLUDED, and ``documented_targets`` de-duplicated in first-seen order.

    Both what the sweep runs (``dotted``, derived from the file's location) and
    what the docstring claims (``documented_targets``, read out of the string),
    from ONE pass — A-213 is precisely the bug of having only the first.

    Cached: it AST-parses every test file (0.17s) and four tests below ask for it,
    so an uncached call was pure repeat in a lane whose whole point is being fast.
    Callers only READ the result; the tuples are immutable on purpose.
    """
    found = []
    for path in _test_py_files():
        tree = _parse(path)
        if tree is None:
            continue
        matches = list(_STANDALONE_CMD_RE.finditer(ast.get_docstring(tree) or ""))
        if not matches:
            continue
        targets = tuple(
            dict.fromkeys(m.group("target") for m in matches if m.group("target"))
        )
        found.append((_rel(path), _file_dotted_path(path), targets))
    return tuple(found)


@lru_cache(maxsize=1)
def _standalone_declared_modules():
    """{dotted path: rel path} for each test module documenting a plain
    ``python3 -m unittest`` invocation, excluding this module itself.

    The SWEEP's view of the scan above. It stays keyed on the path derived from
    the file's location, not on the documented string: that derived path is what
    the fast-lane exemption and the rot baseline name, and — now that
    ``test_documented_standalone_command_names_its_own_module`` proves the two
    agree — probing it is never weaker than probing the documented target, which
    may legitimately be a single-method selector beneath it.
    """
    return {
        dotted: rel
        for rel, dotted, _targets in _standalone_declarations()
        if dotted != _SELF_DOTTED
    }


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


# Process-global leak guard (A-231) — see the module docstring for the shape
# decision, what counts as left behind, and the measured cost.

def _is_frappe_local(node):
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "local"
        and isinstance(node.value, ast.Name)
        and node.value.id == "frappe"
    )


def _under_frappe_local(node):
    """``frappe.local`` itself, or anything reached through it — the write target
    ``frappe.local.flags.redirect_location`` mutates a process global just as
    surely as ``frappe.local.db`` does."""
    while isinstance(node, (ast.Attribute, ast.Subscript)):
        if _is_frappe_local(node):
            return True
        node = node.value
    return False


def _is_frappe_module_slot(node):
    """``sys.modules["frappe"]`` / ``sys.modules["frappe.model.document"]`` — the
    other process global these tests swap, to install a fake frappe."""
    return (
        isinstance(node, ast.Subscript)
        and isinstance(node.value, ast.Attribute)
        and node.value.attr == "modules"
        and isinstance(node.slice, ast.Constant)
        and isinstance(node.slice.value, str)
        and (node.slice.value == "frappe" or node.slice.value.startswith("frappe."))
    )


def _writes_process_globals(tree):
    """Does this module WRITE a frappe process global anywhere?

    An AST walk over assignment TARGETS, not a grep: the module whose leak cost the
    whole suite now writes through ``setattr(frappe.local, name, value)`` and
    contains no ``frappe.local.x =`` text at all, so a text scan would have dropped
    the one file this guard exists for.
    """
    for node in ast.walk(tree):
        targets = []
        if isinstance(node, (ast.Assign, ast.Delete)):
            targets = node.targets
        elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
            targets = [node.target]
        if any(_under_frappe_local(t) or _is_frappe_module_slot(t) for t in targets):
            return True
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in ("setattr", "delattr")
            and node.args
            and _under_frappe_local(node.args[0])
        ):
            return True
    return False


@lru_cache(maxsize=1)
def _process_global_writers():
    """``{dotted: rel}`` for every test module that writes a frappe process global.

    Called only from the site-bound sweep, so the frappe-free lane never pays for
    this tree scan.
    """
    writers = {}
    for path in _test_py_files():
        tree = _parse(path)
        if tree is not None and _writes_process_globals(tree):
            writers[_file_dotted_path(path)] = _rel(path)
    return writers


# [#a231p1] Runs in the probe subprocess; see "Process-global leak guard" in the
# module docstring. argv: <site> <sites_path> <dotted target>.
_PROCESS_GLOBAL_LEAK_PROBE = '''
import json
import os
import sys
import unittest

import frappe
from frappe.tests.utils import FrappeTestCase

site, sites_path, target = sys.argv[1], sys.argv[2], sys.argv[3]
frappe.init(site=site, sites_path=sites_path)
frappe.connect()

null = open(os.devnull, "w")


def typename(value):
    cls = type(value)
    return cls.__module__ + "." + cls.__qualname__


def run(suite):
    return unittest.TextTestRunner(stream=null, verbosity=0).run(suite)


def frappe_modules():
    return {
        name: mod
        for name, mod in sys.modules.items()
        if name == "frappe" or name.startswith("frappe.")
    }


class Canary(FrappeTestCase):
    """The real thing, in the same process: setUpClass calls frappe.db.commit()."""

    def test_a_real_frappe_test_case_still_runs(self):
        self.assertTrue(frappe.db.get_value("DocType", "DocType", "name"))


before, modules_before = dict(frappe.local), frappe_modules()
outcome = run(unittest.TestLoader().loadTestsFromName(target))
after, modules_after = dict(frappe.local), frappe_modules()

leaks = []
for name in sorted(before):
    if name not in after:
        leaks.append("frappe.local." + name + " deleted, was " + typename(before[name]))
    elif type(after[name]) is not type(before[name]):
        leaks.append(
            "frappe.local." + name + " = " + typename(after[name])
            + ", replaced " + typename(before[name])
        )
    elif after[name] is None and before[name] is not None:
        leaks.append("frappe.local." + name + " = None, was " + typename(before[name]))
for name in sorted(set(after) - set(before)):
    value = after[name]
    origin = type(value).__module__ or ""
    if value is None:
        leaks.append("frappe.local." + name + " = None, started UNSET and must end unset")
    elif origin.split(".")[0] in ("apex", "unittest") or origin == target:
        leaks.append("frappe.local." + name + " = " + typename(value) + ", built by the test")
for name in sorted(modules_before):
    if name not in modules_after:
        leaks.append("sys.modules[" + repr(name) + "] removed")
    elif modules_after[name] is not modules_before[name]:
        leaks.append("sys.modules[" + repr(name) + "] replaced by a stand-in")

canary = run(unittest.TestLoader().loadTestsFromTestCase(Canary))
canary_error = ""
for _case, traceback_text in list(canary.errors) + list(canary.failures):
    canary_error = traceback_text.strip().splitlines()[-1]
    break

# testsRun counts tests that STARTED, so a setUpClass that raises leaves it at 0
# with a clean exit — report the target's own errors or "no tests" is undiagnosable.
problems = [
    str(case) + ": " + text.strip().splitlines()[-1]
    for case, text in list(outcome.errors) + list(outcome.failures)
]

print(json.dumps({
    "leaks": leaks,
    "canary": canary_error,
    "tests": outcome.testsRun,
    "problems": problems,
}))
'''

# Generous, because the point is to fail LOUDLY on a hung probe rather than let the
# bench job sit on an InnoDB lock wait; the slowest real probe measured 39.7s.
_LEAK_PROBE_TIMEOUT = 300

# [#a253r1] One retry of a zero-test verdict; see "Why a zero-test probe is retried".
_LEAK_PROBE_ATTEMPTS = 2


def _live_frappe_site():
    """``(site, absolute sites_path)`` when this run has a live site, else None.

    frappe is imported lazily: this module's other half runs in a frappe-free lane
    where the import itself is the thing being blocked.
    """
    try:
        import frappe
    except ImportError:
        return None
    site = getattr(frappe.local, "site", None)
    sites_path = getattr(frappe.local, "sites_path", None)
    if not site or not sites_path or getattr(frappe.local, "db", None) is None:
        return None
    return site, os.path.abspath(sites_path)


def _probe_process_global_leak(dotted, site, sites_path, extra_path=None):
    """Run ``dotted`` in a fresh site-connected interpreter and report what it left.

    REPO_ROOT leads PYTHONPATH so the probe exercises THIS tree, never an ``apex``
    installed elsewhere — a bench install otherwise wins, and it points at trunk.
    """
    pythonpath = [REPO_ROOT] + list(extra_path or [])
    try:
        proc = subprocess.run(
            [sys.executable, "-c", _PROCESS_GLOBAL_LEAK_PROBE, site, sites_path, dotted],
            cwd=sites_path,
            capture_output=True,
            text=True,
            timeout=_LEAK_PROBE_TIMEOUT,
            env={**os.environ, "PYTHONPATH": os.pathsep.join(pythonpath)},
        )
    except subprocess.TimeoutExpired:
        return {
            "leaks": [],
            "canary": f"probe timed out after {_LEAK_PROBE_TIMEOUT}s",
            "tests": 0,
            "problems": [],
        }
    if proc.returncode != 0:
        tail = proc.stderr.strip().splitlines()
        return {
            "leaks": [],
            "canary": tail[-1] if tail else f"probe exit {proc.returncode}",
            "tests": 0,
            # The whole stderr, not just its last line: a probe that dies before it can
            # report is the case with the least evidence and the most need for it.
            "problems": tail[-8:],
        }
    return json.loads(proc.stdout.strip().splitlines()[-1])


def _probe_until_tests_run(dotted, site, sites_path, extra_path=None):
    """``_probe_process_global_leak``, retried while it reports that NOTHING ran.

    Returns the last report, with ``attempts`` and the diagnosis of every discarded
    try folded in, so a module is named only after the retry ALSO ran nothing.
    """
    discarded = []
    for attempt in range(1, _LEAK_PROBE_ATTEMPTS + 1):
        report = _probe_process_global_leak(dotted, site, sites_path, extra_path)
        report["attempts"] = attempt
        if report["tests"]:
            return report
        discarded.extend(report["problems"])
    report["problems"] = discarded
    return report


# [#a231b1] The one leak this detector FOUND is FIXED, not blessed: A-236 gave
# test_portal_token_throttle.py an `_ABSENT`-sentinel snapshot/restore, so the baseline
# is empty and every process-global writer is enforced. See "Leak baseline" above.
_PROCESS_GLOBAL_LEAK_BASELINE = frozenset()


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
                    # The last stderr line of a unittest run is its verdict banner
                    # ("FAILED (errors=1)"), the same string for every cause — keep the
                    # tail, like the leak probe does, so the report names the real error.
                    broken[dotted] = (
                        "\n      ".join(tail[-8:])
                        if tail
                        else f"exit {result.returncode}"
                    )

        regressed = sorted(set(broken) - _STANDALONE_ROT_BASELINE)
        self.assertEqual(
            regressed,
            [],
            "Module(s) documenting a standalone `python3 -m unittest` run that no "
            "longer pass without frappe — the documented command is broken while "
            "bench run-tests stays green (it never takes the fallback branch):\n"
            + "\n".join(f"  {d}  ({declared[d]})\n      {broken[d]}" for d in regressed),
        )

    def test_documented_standalone_command_names_its_own_module(self):
        """A-213: the documented command must name THIS module — read it, don't
        just use it as a trigger.

        The sweep above probes a dotted path computed from the FILE PATH, so it
        stayed green on docstrings printing ``tests.test_x``, a path that resolves
        from nowhere (there is no top-level ``tests/`` package). Seven of those
        shipped and were caught by eye. A failure here means a human copying the
        documented line gets a different result from the one this guard proves.

        Fix the DOCSTRING, never this assertion: the derived path is the truth,
        because it is what CI, the probe, and ``loadTestsFromName`` all resolve.
        """
        declarations = _standalone_declarations()
        self.assertGreater(
            len(declarations), 10, "standalone-claim scan found implausibly few modules"
        )

        mismatched = [
            f"  {rel}\n      documented: {target}\n      actual:     {dotted}"
            for rel, dotted, targets in declarations
            for target in targets
            if not _target_names_module(target, dotted)
        ]
        self.assertEqual(
            mismatched,
            [],
            "Module(s) documenting a `python3 -m unittest` target that is not their "
            "own dotted path — the printed command fails for a human while the probe "
            "passes on the path derived from the file's location:\n"
            + "\n".join(mismatched),
        )

        # Guard-of-the-guard: an every-target-is-fine verdict is only worth
        # anything if targets were actually READ. Should the capture group ever
        # stop capturing, the comprehension above would sweep an empty set and
        # pass for the wrong reason — this lists every module it read nothing from.
        unreadable = sorted(rel for rel, _dotted, targets in declarations if not targets)
        self.assertEqual(
            unreadable,
            [],
            "Module(s) declaring a standalone run whose documented target this guard "
            "could not read — write it as a dotted path (`apex.<pkg>.<module>`, "
            "optionally narrowed to a Class or method) so the claim is checkable and "
            "not merely runnable-looking:\n" + "\n".join(f"  {r}" for r in unreadable),
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


class TestProcessGlobalWriterScan(unittest.TestCase):
    """A-231 self-tests for the at-risk population scan. Synthetic snippets only —
    no tree scan, so the frappe-free fast lane pays nothing for them."""

    def _writes(self, src):
        return _writes_process_globals(ast.parse(src))

    def test_reads_every_shape_that_can_strand_a_stub(self):
        # [#a231t1] Each of these is live in this tree today.
        for label, src in (
            ("plain attribute assign", "frappe.local.db = fake\n"),
            ("nested attribute assign", "frappe.local.flags.redirect_location = '/x'\n"),
            ("setattr, the shape a grep misses", "setattr(frappe.local, name, value)\n"),
            ("delattr", "delattr(frappe.local, 'db')\n"),
            ("del statement", "del frappe.local.db\n"),
            ("sys.modules swap", "sys.modules['frappe'] = _FakeFrappe()\n"),
            ("sys.modules submodule swap", "sys.modules['frappe.model.document'] = mod\n"),
        ):
            with self.subTest(label):
                self.assertTrue(self._writes(src), src)

    def test_ignores_a_read_and_an_unrelated_write(self):
        # [#a231t2] The last two are the documented BOUNDARY, not an oversight:
        # neither is a write the frappe.local diff can observe.
        for label, src in (
            ("read through the proxy", "user = frappe.local.session.user\n"),
            ("defaulted read", "value = getattr(frappe.local, 'db', None)\n"),
            ("a local variable that happens to be named local", "local = C()\nlocal.db = 1\n"),
            ("another app's sys.modules slot", "sys.modules['erpnext'] = mod\n"),
            ("a bare frappe module attribute", "frappe.sendmail = fake\n"),
        ):
            with self.subTest(label):
                self.assertFalse(self._writes(src), src)


class _ScriptedProbe:
    """A stand-in for the subprocess probe that replays a scripted list of reports.

    The last entry is sticky, so "always returns nothing" is one entry rather than a
    count that has to be kept in step with ``_LEAK_PROBE_ATTEMPTS``.
    """

    def __init__(self, *reports):
        self.reports = reports
        self.calls = []

    def __call__(self, dotted, site, sites_path, extra_path=None):
        self.calls.append(dotted)
        return dict(self.reports[min(len(self.calls), len(self.reports)) - 1])


def _report(tests, problems=()):
    return {"leaks": [], "canary": "", "tests": tests, "problems": list(problems)}


_DEADLOCK = "setUpClass (x.TestX): frappe.exceptions.QueryDeadlockError: (1020, ...)"


class TestZeroTestProbeIsRetried(unittest.TestCase):
    """A-253: a probe that ran nothing is retried before its module is named.

    Deliberately frappe-free — the retry is scheduling logic over a report dict, so
    proving it must not cost a live site, and the fast lane checks it too.
    """

    def _retry(self, probe):
        with mock.patch(__name__ + "._probe_process_global_leak", probe):
            return _probe_until_tests_run("apex.some.test_victim", "test", "/sites")

    def test_a_probe_that_ran_tests_is_never_retried(self):
        """The cost claim: on a healthy run the retry is free, not merely cheap."""
        probe = _ScriptedProbe(_report(7))
        report = self._retry(probe)
        self.assertEqual(report["tests"], 7)
        self.assertEqual(report["attempts"], 1)
        self.assertEqual(len(probe.calls), 1)

    def test_one_zero_test_return_is_absorbed_by_the_retry(self):
        """The flake, forced ONCE: the second answer stands and nothing is named."""
        probe = _ScriptedProbe(_report(0, [_DEADLOCK]), _report(22))
        report = self._retry(probe)
        self.assertEqual(report["tests"], 22, "the retry's real answer must win")
        self.assertEqual(report["attempts"], _LEAK_PROBE_ATTEMPTS)
        self.assertEqual(len(probe.calls), 2)

    def test_a_module_that_runs_nothing_every_time_is_still_reported(self):
        """The hole a retry could open, forced ALWAYS: an empty module stays named,
        and every attempt's diagnosis is carried so the site cause is readable."""
        probe = _ScriptedProbe(_report(0, [_DEADLOCK]))
        report = self._retry(probe)
        self.assertEqual(report["tests"], 0, "giving up must still report zero")
        self.assertEqual(report["attempts"], _LEAK_PROBE_ATTEMPTS)
        self.assertEqual(len(probe.calls), _LEAK_PROBE_ATTEMPTS)
        self.assertEqual(report["problems"], [_DEADLOCK] * _LEAK_PROBE_ATTEMPTS)


class TestNoTestModuleLeaksProcessGlobals(unittest.TestCase):
    """A-231: no test module may strand a stub in a frappe process global.

    Every method here needs a live site, because the decisive half of the check is a
    REAL ``FrappeTestCase`` running in the same interpreter as the module under test.
    The frappe-free lane skips the class outright.
    """

    _LEAKY_PLANT = (
        "import unittest\n"
        "from types import SimpleNamespace\n"
        "import frappe\n\n\n"
        "class TestPlantedLeak(unittest.TestCase):\n"
        "    def setUp(self):\n"
        "        frappe.local.db = SimpleNamespace(get_value=lambda *a, **k: None)\n\n"
        "    def test_passes_in_isolation(self):\n"
        "        self.assertIsNone(frappe.local.db.get_value('DocType', 'DocType', 'name'))\n"
    )

    _ABSENT_PLANT = (
        "import unittest\n"
        "import frappe\n\n\n"
        "class TestPlantedAbsent(unittest.TestCase):\n"
        "    def setUp(self):\n"
        "        original = getattr(frappe.local, 'request', None)\n"
        "        self.addCleanup(setattr, frappe.local, 'request', original)\n"
        "        frappe.local.request = object()\n\n"
        "    def test_passes_in_isolation(self):\n"
        "        self.assertIsNotNone(frappe.local.request)\n"
    )

    _RESTORING_PLANT = (
        "import unittest\n"
        "from types import SimpleNamespace\n"
        "import frappe\n\n"
        "_ABSENT = object()\n\n\n"
        "class TestPlantedRestore(unittest.TestCase):\n"
        "    def setUp(self):\n"
        "        original = getattr(frappe.local, 'db', _ABSENT)\n"
        "        self.addCleanup(self._restore, original)\n"
        "        frappe.local.db = SimpleNamespace(get_value=lambda *a, **k: None)\n\n"
        "    @staticmethod\n"
        "    def _restore(original):\n"
        "        if original is _ABSENT:\n"
        "            delattr(frappe.local, 'db')\n"
        "        else:\n"
        "            frappe.local.db = original\n\n"
        "    def test_passes_in_isolation(self):\n"
        "        self.assertIsNone(frappe.local.db.get_value('DocType', 'DocType', 'name'))\n"
    )

    # [#a253e1] Imports and loads, defines no test — the shape the retry must still
    # name, since a testless module is a real finding and not a lost slot.
    _EMPTY_PLANT = "import frappe\n\nOK = bool(frappe)\n"

    def setUp(self):
        self.live = _live_frappe_site()
        if self.live is None:
            self.skipTest(
                "needs a live frappe site — a FrappeTestCase canary cannot run in the "
                "frappe-free lane, and this guard is meaningless without one"
            )

    def _probe_plant(self, source):
        """Write ``source`` as a throwaway module and probe it, returning the report."""
        site, sites_path = self.live
        with tempfile.TemporaryDirectory() as tmp:
            name = "apex_a231_plant"
            with open(os.path.join(tmp, name + ".py"), "w", encoding="utf-8") as fh:
                fh.write(source)
            return _probe_until_tests_run(name, site, sites_path, extra_path=[tmp])

    def test_the_probe_catches_a_stub_that_is_never_put_back(self):
        """Guard-of-the-guard, and the incident replayed: a module that stubs
        ``frappe.local.db`` and walks away must be caught by BOTH halves.

        Validated against the real pre-fix revision of
        ``habitat/report/checkout_pending_clearance/test_checkout_pending_clearance
        .py`` while this guard was written; the plant below is that file's defect
        reduced to its bones, so the proof stays runnable instead of being a claim
        about a commit nobody re-checks.
        """
        report = self._probe_plant(self._LEAKY_PLANT)
        self.assertEqual(report["tests"], 1, "the planted module did not run — probe broke")
        self.assertTrue(
            any("SimpleNamespace" in leak for leak in report["leaks"]),
            f"the frappe.local diff missed a stranded db stub: {report['leaks']}",
        )
        self.assertIn(
            "has no attribute 'commit'",
            report["canary"],
            "the canary did not die the way the whole suite died — it is not proving "
            "the consequence, only the diff is",
        )

    def test_the_probe_catches_an_unset_global_left_as_none(self):
        """The absent-attribute case, which the canary CANNOT see.

        ``frappe.local`` is a werkzeug ``Local``: an unset name raises AttributeError
        and is not listed at all, so restoring a snapshot taken with ``getattr(...,
        None)`` turns unset into None. Nothing breaks today, which is exactly why
        only the diff can catch it — the canary here must stay clean.
        """
        report = self._probe_plant(self._ABSENT_PLANT)
        self.assertEqual(report["tests"], 1, "the planted module did not run — probe broke")
        self.assertIn(
            "frappe.local.request = None, started UNSET and must end unset",
            report["leaks"],
        )
        self.assertEqual(report["canary"], "", "this plant is harmless — the canary must pass")

    def test_the_probe_clears_a_stub_that_is_put_back(self):
        """The negative control: a detector that reds on everything proves nothing.

        Same stub as the leaking plant, restored through an ``_ABSENT`` sentinel that
        DELETES an originally-unset attribute rather than writing None over it.
        """
        report = self._probe_plant(self._RESTORING_PLANT)
        self.assertEqual(report["tests"], 1, "the planted module did not run — probe broke")
        self.assertEqual(report["leaks"], [], "a correctly restored stub must read clean")
        self.assertEqual(report["canary"], "")

    def test_a_genuinely_testless_module_survives_the_retry_and_is_still_named(self):
        """A-253's hole, closed against a REAL probe rather than a scripted one.

        The retry that absorbs a deadlocked slot must not also absorb a module that
        truly runs nothing: this plant loads cleanly and defines no test, so both
        attempts honestly return zero and the sweep names it.
        """
        report = self._probe_plant(self._EMPTY_PLANT)
        self.assertEqual(report["tests"], 0)
        self.assertEqual(report["attempts"], _LEAK_PROBE_ATTEMPTS, "it must be RETRIED, not named on the first zero")
        self.assertEqual(report["problems"], [], "nothing failed here — the module simply has no tests")

    def test_no_test_module_strands_a_stub_in_a_frappe_process_global(self):
        """The sweep: every module that writes a process global must put it back.

        A failure means the module named below leaves something behind in
        ``frappe.local`` (or in ``sys.modules``), which will abort every test that
        runs after it under ``bench run-tests`` while the module itself still passes
        alone. Fix the OWNING module — snapshot before the write, restore through
        ``addCleanup``, and treat an originally-unset attribute as unset, not None.
        """
        import frappe

        site, sites_path = self.live
        writers = _process_global_writers()
        self.assertGreater(len(writers), 10, "at-risk scan found implausibly few modules")

        # The probes run real site tests; releasing this run's row locks first keeps
        # them off a 50s InnoDB lock wait apiece. This guard writes nothing itself.
        frappe.db.rollback()

        # Serial on purpose — 18 interpreters against one site DB corrupts the
        # verdict for a 17s saving. See the docstring's measurement.
        reports = {
            dotted: _probe_until_tests_run(dotted, site, sites_path)
            for dotted in sorted(writers)
        }

        unprobeable = sorted(d for d, r in reports.items() if not r["tests"])
        self.assertEqual(
            unprobeable,
            [],
            "Probe(s) that ran NO tests on EVERY attempt — a clean verdict from them "
            "means nothing, so they are failed rather than counted. Read the diagnosis "
            "below before touching the module: a QueryDeadlockError or a connection "
            "error is this shared site, not this module.\n"
            + "\n".join(
                f"  {d}  ({writers[d]}, {reports[d]['attempts']} attempts)\n      "
                + "\n      ".join(reports[d]["problems"] or [reports[d]["canary"] or "no tests found"])
                for d in unprobeable
            ),
        )

        leaking = {d: r for d, r in reports.items() if r["leaks"] or r["canary"]}
        regressed = sorted(set(leaking) - _PROCESS_GLOBAL_LEAK_BASELINE)
        self.assertEqual(
            regressed,
            [],
            "Test module(s) leaving a stub in a frappe process global — every later "
            "test in the same interpreter inherits it, while this module still passes "
            "on its own:\n"
            + "\n".join(
                f"  {d}  ({writers[d]})\n      "
                + "\n      ".join(leaking[d]["leaks"] + ([leaking[d]["canary"]] if leaking[d]["canary"] else []))
                for d in regressed
            ),
        )

        stale = sorted(_PROCESS_GLOBAL_LEAK_BASELINE - set(writers))
        self.assertEqual(
            stale,
            [],
            f"leak-baseline entr(ies) that no longer write a process global at all — "
            f"prune them, they exempt nothing: {stale}",
        )
        cleaned = sorted(_PROCESS_GLOBAL_LEAK_BASELINE - set(leaking))
        self.assertEqual(
            cleaned,
            [],
            "leak-baseline entr(ies) that no longer leak — prune them so the baseline "
            "cannot quietly re-absorb a future regression:\n"
            + "\n".join(f"  {d}" for d in cleaned),
        )


if __name__ == "__main__":
    unittest.main()
