# Copyright (c) 2026, AFMCO and contributors
"""Agent-change hygiene guard (A-056): duplicate / dead / copied / orphan / non-native code.

Pure-Python, no live Frappe site required — same family as test_release_hygiene.py,
test_sql_interpolation_guard.py and test_no_cross_test_imports.py.

Mechanises the read-before-write rule (feedback-read-before-write-code-guard): an
agent must inventory the existing and native implementation before adding new code.
Five narrow, low-false-positive static checks. Each is a RATCHET over a frozen
baseline, exactly like test_no_cross_test_imports.py's ``_BASELINE`` and
test_sql_interpolation_guard.py's ``SAFE_ALLOWLIST``: today's tree seeds the
baseline (documented, pre-existing), and only a finding beyond it fails the build —
so this guard blocks future regressions without demanding an unrelated cleanup PR.

Scan universe (A-170): checks 1 and 2 read PRODUCTION **AND TEST** files. They used
to share ``_production_py_files()``, which skips ``tests/`` and every ``test_*.py``,
so a helper duplicated across two test modules was invisible to CI — a near-duplicated
workspace-reachability scan was caught only by a card's goal text, never by a guard.
Checks 3-5 stay production-only ON PURPOSE: check 4 (dead modules) declares a file
dead when nothing imports it, and a test module is *never* imported by anything, so
widening it flags 348 of the 352 test files (measured); checks 3/5 scan DocType JSON
and native-primitive imports, neither of which a test file owns. Only the two
duplication detectors gain anything from test coverage, so only they were widened.

Baselines. Widening check 1 to tests added exactly 4 names. One
(``tearDownModule``, bound in 17 files) is unittest dispatch and went to
DISPATCH_NAMES; the other 3 were real: a test module bound a module-level
unwrapping shim under the SAME public name as the production Number Card method it
wraps, so a grep for the API name landed on the test's redefinition. A-176 renamed
all three to ``_<card>_value`` (private, and no longer a production API name), so
_DUP_NAME_BASELINE holds only production parallel structure again.

Widening check 2 to tests found 21 groups / 64 functions of pre-existing duplication,
all fixture/assertion helpers pasted between test modules rather than promoted into
tests/factories.py (P-135's shared home). A-176 drained that set to ZERO: every one
was promoted into factories.py, tests/_helpers.py or tests/source_tree.py — a
non-``test_`` sibling each time, because test_no_cross_test_imports.py forbids a test
module importing a test module — and its group left _COPY_PASTE_BASELINE in the same
commit, so the frozen set only ever shrank. What remains below is production-only
debt; a test-tree entry reappearing there is a regression, not a baseline.

A-176 then audited all 8 surviving PRODUCTION groups one by one and found NOT ONE
incidental match — every pair either carries a docstring admitting it mirrors the
other, or is a byte-identical helper. So the guard needs no "coincidental" category:
building one would be dead flexibility for an empty set, and the honest way to make
the baseline mean one thing was the opposite move — prove every entry is real, give
each a written reason for surviving, and add test_baseline_holds_no_stale_group so a
fixed entry can no longer linger. Three of the eight were promoted in that pass
(auto_email_report_seed_base, accommodation_stock_ledger.reverse_and_mark_cancelled,
finding_fanout.is_actionable).

A later wave owning salis/ took three more, leaving TWO. Its lesson is why the
surviving reasons are worth reading: two of those three copies had DRIFTED, so
"fold one onto the other" was the wrong move twice. The _is_staff pair read
same-named STAFF_ROLES tuples with different members, so only the membership test
was shared (salis.utils.has_any_role) and each role SET stayed local — folding them
would have let a Finance Manager authorise a boarding scan. What is left is the
patch pair, retained on merit since a patch that has already run everywhere gains
nothing from refactoring, and the HR-recipient pair, blocked by habitat/ write
scope rather than the salis/ scope previously recorded against it.

  1. TestDuplicateTopLevelFunctionNames — two different files each bind
     a same-named PUBLIC module-level function. Scoped to module level (a Document
     subclass's own methods live inside the ClassDef body, which this scan never
     enters) and to public names: this codebase's "detached controller" style wires
     hooks.py doc_events to bare module-level functions named after the lifecycle
     event (e.g. habitat/doctype/building/building.py has an EMPTY
     ``class Building(Document): pass`` beside module-level ``before_save`` /
     ``on_update``); those names, plus report/page/patch entry points such as
     ``execute`` / ``get_context``, recur across dozens of files BY DESIGN, so they
     are excluded via DISPATCH_NAMES rather than producing wall-to-wall noise. A
     leading underscore is this codebase's established file-private-helper
     convention (one controller file alone — building.py — binds 18 of them);
     flagging those would be almost all false positives, so only PUBLIC names count.

  2. TestCopyPastedFunctionBodies — two functions (any name, any file, any nesting)
     whose bodies are structurally identical (same statements, operators AND
     literal values — comments/whitespace/docstrings never matter) and non-trivial
     in size (>= 3 real statements, so a common one-line stub never matches).
     Independent of naming, so a rename-and-paste is still caught; independent of
     file, so even a same-file paste is caught.

     Test code repeats itself far more than production code, so covering tests
     needed a SHAPE, not a looser threshold. Raising the minimum statement count
     was rejected: it buys silence by going blind (min=8 leaves 1 of 37 test
     groups, but a 3-statement fixture builder — the exact helper this check
     exists to catch — vanishes with it). Instead the threshold stays at 3
     everywhere and a test file's UNITTEST-DISPATCHED functions are skipped: a
     name unittest itself dispatches (``test*`` per TestLoader.testMethodPrefix,
     plus setUp/tearDown/setUpClass/tearDownClass/setUpModule/tearDownModule)
     that ALSO declares no parameter beyond self/cls. Those recur by nature and
     were 16 of the 37 raw test groups. The no-parameter half of the rule is what
     stops the laundering: a shared fixture builder takes arguments, so renaming
     it ``test_make_x(building, room)`` does not buy it the exemption. Every one
     of the 21 groups left is a genuine duplicated helper.

  3. TestOrphanDocTypes — a ``doctype/<x>/<x>.json`` whose declared ``module`` is
     not a name registered in modules.txt, or whose on-disk module folder does not
     match the scrub() of its own declared module. Frappe only loads a DocType
     whose module is a real, installed Module Def — either mismatch ships dead.

  4. TestDeadProductionModules — a production .py file that (a) no other .py
     file imports, (b) no hooks.py / patches.txt / JSON string names by dotted
     path, (c) is not a Frappe-by-convention dynamically-loaded controller
     (doctype/report/page/web_form/notification controller, or a www/ page
     controller), and (d) ships no ``@frappe.whitelist`` endpoint (HTTP-reachable
     with zero Python-side imports). Deliberately Python-only — JS/Vue dead-code
     is a separate, much larger problem and out of this guard's pragmatic scope.

  4b. TestDeadProductionFunctions — the same question one level down: a
     module-level ``def`` inside a LIVE file that nothing can reach. Check 4
     cannot see these, because a single live sibling keeps the whole file
     referenced. A def is reachable if any .py mentions its bare name (a call,
     or a barrel's ``from … import x`` re-export), an ``__all__`` names it, a
     dotted path ending in it appears in any .py/.json/.js/.html/.md/patches.txt
     (hooks, Number Card ``method``, frappe.enqueue, frappe.call from Desk JS,
     or a documented ``bench execute`` operator command), it carries
     ``@frappe.whitelist``, or its name is a DISPATCH_NAMES lifecycle hook.
     The reference universe is deliberately WIDER than check 4's: it adds .js,
     .html and the published docs, because at function granularity check 4's
     "any module holding a whitelist is exempt" shortcut is far too coarse —
     226 endpoints here are named only from Desk JS, and three patch entry
     points are named only in docs/administration/identity-upgrade.md.

     Its ``_DEAD_FUNCTION_BASELINE`` seeded 8 pre-existing dead defs and is now
     EMPTY — each was deleted, not re-wired, so the check is an outright gate
     again. Five were settings accessors every real reader already bypassed with
     ``frappe.get_single()`` (habitat_settings ``get_settings`` /
     ``get_default_currency`` / ``validate_posting_period``,
     payment_routing_settings ``get_routing_settings``, salis_settings
     ``get_salis_settings``); ``validate_posting_period`` also duplicated a native
     guard, since erpnext/hooks.py binds ``validate_accounting_period_on_doc_save``
     to every ``period_closing_doctypes`` entry. One was
     masar_worker_token ``_driver_token_from_request``, a driver-side twin of
     salis/api/masar.py ``_token_from_request`` that live callers bypass by
     reaching ``presented_token(DRIVER)`` directly. One was habitat_dashboard_seed
     ``seed_all_dashboards``, a no-op stub whose docstring claimed an
     after_migrate/after_install entrypoint no hook ever named (its two wired
     siblings stay). The last was setup_wizard ``get_setup_stages``, and it is the
     reason this list is worth reading: its docstring claimed the
     ``setup_wizard_stages`` hook, which apex/hooks.py never declares. Declaring
     it would NOT have been the fix — frappe concatenates the stage hooks and the
     setup_wizard_complete hooks into ONE run (frappe/desk/page/setup_wizard/
     setup_wizard.py:36), and the declared ``setup_wizard_complete`` already
     applies the same configuration, so wiring it would have double-applied setup.

  5. TestNativePrimitiveBypass — a hand-rolled reimplementation of a short, NAMED
     list of Frappe primitives (currently: raw smtplib instead of
     ``frappe.sendmail``; raw ``uuid`` instead of ``frappe.generate_hash``) with no
     ``# native-ok: <reason>`` justification on the same line — the same
     "justify or don't" contract as permissions-guard.yml's ``# audit-ok``. Kept
     deliberately short: each entry names a primitive with NO legitimate exception
     found in this repo today (e.g. ``hashlib.sha256`` is intentionally NOT listed —
     P-104's Masar Worker Token hash-at-rest is a correct, already-reviewed use
     that ``frappe.generate_hash`` cannot replace, since generate_hash mints a new
     random value rather than hashing an existing secret).

Run standalone (from the repo root, so ``apex.tests.source_tree`` resolves):
  python3 -m unittest apex.tests.test_duplicate_and_dead_code_guard -v
"""

import ast
import copy
import glob
import json
import os
import re
import unittest

# Scan universes, aliased to say what each check reads: 3-5 stay production-only
# (a test file can only add noise to them), 1-2 read production AND test.
from apex.tests.source_tree import (
    APP_ROOT,
    REPO_ROOT,
    all_py_files as _scanned_py_files,
    file_dotted_path as _file_dotted_path,
    is_test_file as _is_test_file,
    parse as _parse,
    production_py_files as _production_py_files,
    rel as _rel,
)

MODULES_TXT = os.path.join(APP_ROOT, "modules.txt")
PATCHES_TXT = os.path.join(APP_ROOT, "patches.txt")


def _scrub(name):
    """Pure-python mirror of frappe.scrub() (no live site needed)."""
    return name.strip().lower().replace(" ", "_").replace("-", "_")


# 1. Duplicate top-level (module-scope) function names

# [#a056dn] Frappe dispatch / lifecycle names that recur across dozens of files
# BY DESIGN (see module docstring) — never a duplication smell.
DISPATCH_NAMES = {
    "execute", "get_context", "get_data", "get_list_context", "get_indicator",
    "get_dashboard_data", "get_permission_query_conditions", "has_permission",
    "has_website_permission", "get_columns", "get_chart_data", "boot_session",
    "on_login", "on_logout",
    "validate", "before_validate", "before_insert", "after_insert",
    "before_save", "on_update", "before_submit", "on_submit",
    "before_cancel", "on_cancel", "on_trash", "after_delete",
    "on_change", "on_update_after_submit", "before_rename", "after_rename",
    "before_print", "before_workflow_action", "after_workflow_action",
    "before_migrate", "after_migrate", "after_install", "before_tests",
    "before_request", "after_request", "on_doctype_update",
    # [#a170dn] unittest's own module-level dispatch hooks — the test-tree analogue
    # of the Frappe lifecycle names above (17 files bind tearDownModule by design).
    "setUpModule", "tearDownModule", "load_tests",
}

# [#a170lc] unittest's class/method-level dispatch names. Paired with the
# no-extra-parameter rule in _is_unittest_dispatched (see module docstring).
UNITTEST_LIFECYCLE_NAMES = {
    "setUp", "tearDown", "setUpClass", "tearDownClass",
    "setUpModule", "tearDownModule",
}


def _module_level_funcs(tree):
    """FunctionDef/AsyncFunctionDef bound directly in the module body. A Document
    subclass's own methods live inside its ClassDef body — ``tree.body`` never
    recurses into a ClassDef, so a class method is never mistaken for one of these."""
    return [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]


def _duplicate_def_names():
    """{name: sorted[rel_paths]} for every PUBLIC top-level def name bound in 2+
    different files (production or test) that is not a DISPATCH_NAMES entry."""
    by_name = {}
    for path in _scanned_py_files():
        tree = _parse(path)
        if tree is None:
            continue
        for fn in _module_level_funcs(tree):
            if fn.name.startswith("_") or fn.name in DISPATCH_NAMES:
                continue
            by_name.setdefault(fn.name, set()).add(_rel(path))
    return {name: sorted(paths) for name, paths in by_name.items() if len(paths) > 1}


# [#a056b1] Baseline frozen at guard-authoring time (2026-07-22): names already
# bound in 2+ files today. A name is a NEW violation only once its current file
# set stops being a subset of its baseline set (a brand-new colliding name, or an
# existing collision gaining another file) — see test_no_new_or_grown_duplicate.
# Every entry below is independently-implemented parallel structure across
# sibling doctypes/portals (verified while authoring this guard), not a case of
# one file actually reusing another's code under a copied name.
_DUP_NAME_BASELINE = {
    "get_default_company": [
        "apex_core/doctype/habitat_settings/habitat_settings.py",
        "apex_core/doctype/salis_settings/salis_settings.py",
    ],
    "get_my_vehicle": [
        "salis/api/driver_portal/profile.py",
        "salis/api/fleet_employee.py",
    ],
    "get_trip_boarding": [
        "salis/api/boarding_flow.py",
        "salis/api/route_supervisor.py",
    ],
    "get_vehicle_timeline": [
        "salis/api/fleet_os.py",
        "salis/api/operations_control.py",
    ],
    "has_apps_screen_access": [
        "www/fleet.py",
        "www/fleet_os.py",
        "www/housing.py",
        "www/masar_supervisor.py",
        "www/safety.py",
    ],
    "is_configured": [
        "salis/api/messaging_gateway.py",
        "salis/api/web_push.py",
    ],
    "load_template_into_doc": [
        "habitat/doctype/maintenance_material_template/maintenance_material_template.py",
        "salis/doctype/vehicle_handover_checklist_template/vehicle_handover_checklist_template.py",
    ],
    "mark_completed": [
        "habitat/doctype/maintenance_work_order/maintenance_work_order.py",
        "habitat/doctype/scheduled_task_instance/scheduled_task_instance.py",
        "habitat/doctype/subcontractor_service_order/subcontractor_service_order.py",
    ],
    "start_work": [
        "habitat/doctype/maintenance_work_order/maintenance_work_order.py",
        "habitat/doctype/subcontractor_service_order/subcontractor_service_order.py",
    ],
    "submit_fuel_request": [
        "salis/api/driver_portal/fuel.py",
        "salis/api/fleet_employee.py",
    ],
    "toggle_service": [
        "habitat/doctype/bed/bed.py",
        "habitat/doctype/room/room.py",
    ],
}


class TestDuplicateTopLevelFunctionNames(unittest.TestCase):
    def test_scan_finds_production_files(self):
        self.assertTrue(_production_py_files(), "production .py scan found nothing — path broke")

    def test_duplication_scan_universe_includes_test_files(self):
        # [#a170t1] The A-170 blind spot itself: assert the widened universe really
        # holds test modules, central and colocated, and that it is a strict superset.
        scanned = {_rel(p) for p in _scanned_py_files()}
        production = {_rel(p) for p in _production_py_files()}
        self.assertLess(production, scanned, "widened scan must strictly contain production")
        self.assertIn(os.path.basename(__file__), [os.path.basename(p) for p in scanned])
        self.assertIn("tests/factories.py".replace("/", os.sep), scanned)
        self.assertTrue(
            any(_is_test_file(rel) and os.sep in rel and not rel.startswith("tests") for rel in scanned),
            "colocated test_*.py files must be in the duplication scan universe",
        )

    def test_detector_ignores_dispatch_names_and_private_helpers(self):
        # [#a056t1]
        src = (
            "def validate(doc, method=None):\n    pass\n\n"
            "def _helper(doc):\n    pass\n"
        )
        tree = ast.parse(src)
        names = {fn.name for fn in _module_level_funcs(tree)}
        self.assertEqual(names, {"validate", "_helper"})
        # both would be excluded by the real scan's filters:
        self.assertIn("validate", DISPATCH_NAMES)
        self.assertTrue("_helper".startswith("_"))

    def test_no_new_or_grown_duplicate_public_function_name(self):
        found = _duplicate_def_names()
        offenders = {
            name: paths
            for name, paths in found.items()
            if not set(paths) <= set(_DUP_NAME_BASELINE.get(name, ()))
        }
        self.assertEqual(
            offenders,
            {},
            "New duplicate top-level function name(s). Read-before-write: search for "
            "the existing definition first and import/reuse it instead of redefining "
            "it under the same name in a new file (or rename yours if it is genuinely "
            "unrelated):\n"
            + "\n".join(f"  {n}: {p}" for n, p in sorted(offenders.items())),
        )


# 2. Copy-pasted function bodies

def _all_funcs(tree):
    """Every FunctionDef/AsyncFunctionDef at any nesting level — copy-paste can
    hit a class method just as easily as a free function."""
    return [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]


def _non_docstring_body(fn_node):
    body = fn_node.body
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        return body[1:]
    return body


def _local_bindings(fn_node):
    """``{original: placeholder}`` for every name the function BINDS ITSELF,
    numbered in BINDING order — parameters in signature order, then assignment
    targets in source order.

    Binding order, never use order. With use order, ``load(a)`` and ``load(b)``
    inside a two-parameter function would both number their argument first and
    collapse into one signature, inventing a match between two functions that
    call the same helper on different inputs (test_signature_numbers_locals_by_
    binding_order_not_use_order pins this).

    A bound name is EXCLUDED when the name is the identity of something outside
    the function rather than a private label: an import binding (in
    ``from m import alpha``, ``alpha`` names the imported symbol), a
    ``global``/``nonlocal`` declaration, or a nested def/class, which a decorator
    can register by name."""
    external = set()
    for node in ast.walk(fn_node):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            external.update((a.asname or a.name).split(".")[0] for a in node.names)
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            external.update(node.names)
        elif node is not fn_node and isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ):
            external.add(node.name)

    args = fn_node.args
    ordered = [
        a.arg
        for a in (*args.posonlyargs, *args.args, args.vararg, *args.kwonlyargs, args.kwarg)
        if a
    ]
    placed = []
    for node in ast.walk(fn_node):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            placed.append((node.lineno, node.col_offset, node.id))
        elif isinstance(node, ast.ExceptHandler) and node.name:
            placed.append((node.lineno, node.col_offset, node.name))
    ordered += [name for _lineno, _col, name in sorted(placed)]

    mapping = {}
    for name in ordered:
        if name not in external and name not in mapping:
            mapping[name] = f"_v{len(mapping)}"
    return mapping


class _AlphaRename(ast.NodeTransformer):
    """Rewrites ONLY the identifiers listed in the local-binding map.

    Attribute names, constants and keyword-argument names sit in ``str`` fields of
    other node types, which this visitor structurally never reaches — so a field
    name, a DocType string or a ``for_update=True`` keyword cannot be normalised
    away by a future edit here either."""

    def __init__(self, mapping):
        self._map = mapping

    def visit_Name(self, node):
        node.id = self._map.get(node.id, node.id)
        return node

    def visit_arg(self, node):
        node.arg = self._map.get(node.arg, node.arg)
        return node

    def visit_ExceptHandler(self, node):
        self.generic_visit(node)
        if node.name:
            node.name = self._map.get(node.name, node.name)
        return node


def _body_signature(fn_node):
    """Structural signature of a function's body, alpha-renamed over the locals the
    function binds itself, so a paste that renames them still matches.

    ABSTRACTED, because the name is a private label carrying no meaning outside the
    body: parameter names — including the ``self``/``doc`` split this codebase's
    detached-controller style produces for one lifecycle body — and every name bound
    by assignment, ``for``, ``with ... as``, walrus or ``except ... as``.

    KEPT VERBATIM, because the name IS the meaning and normalising it would make two
    genuinely different functions look identical: attribute and field names, string
    and numeric literals (DocType names, fieldnames, status values), keyword-argument
    names, and every FREE name — module-level helpers, imported symbols, constants.

    Telling them apart needs no hand-written name list. Bound-vs-free is read off the
    AST by ``_local_bindings``; the other three classes are unreachable from
    ``_AlphaRename`` by construction. Operators and literal values stay significant,
    so a copy-paste-with-one-value-changed still does not match (kept strict to stay
    low-false-positive; see module docstring).

    Statement ORDER stays significant on purpose — test_signature_stays_order_
    sensitive carries the measurement behind that."""
    clone = copy.deepcopy(fn_node)
    _AlphaRename(_local_bindings(clone)).visit(clone)
    return "\n".join(
        ast.dump(stmt, annotate_fields=False) for stmt in _non_docstring_body(clone)
    )


def _signature_of(src, name):
    """The signature of function ``name`` parsed out of the literal source ``src`` —
    the fixture the signature's own unit tests are written against."""
    by_name = {fn.name: fn for fn in _all_funcs(ast.parse(src))}
    return _body_signature(by_name[name])


def _is_unittest_dispatched(fn_node):
    """True for a function unittest CALLS rather than one the author wrote to be
    reused: a dispatched name (``test*`` — TestLoader.testMethodPrefix — or a
    lifecycle hook) that also takes no parameter beyond the implicit self/cls.
    Only applied inside test files. The parameter half is load-bearing: a shared
    fixture builder takes arguments, so it cannot buy the exemption by renaming
    itself ``test_...``."""
    if not (fn_node.name.startswith("test") or fn_node.name in UNITTEST_LIFECYCLE_NAMES):
        return False
    args = fn_node.args
    positional = len(args.posonlyargs) + len(args.args)
    return positional <= 1 and not args.kwonlyargs and args.vararg is None and args.kwarg is None


def _copy_pasted_groups():
    """{signature: sorted[(rel_path, lineno, func_name), ...]} for every function
    body of >= 3 real statements that structurally matches another function's body,
    across production AND test files."""
    by_sig = {}
    for path in _scanned_py_files():
        tree = _parse(path)
        if tree is None:
            continue
        rel = _rel(path)
        is_test = _is_test_file(rel)
        for fn in _all_funcs(tree):
            if len(_non_docstring_body(fn)) < 3:
                continue
            if is_test and _is_unittest_dispatched(fn):
                continue
            by_sig.setdefault(_body_signature(fn), set()).add((rel, fn.lineno, fn.name))
    return {sig: sorted(locs) for sig, locs in by_sig.items() if len(locs) > 1}


# [#a056b2] Baseline of bodies already shared today. Line numbers are excluded from
# the key so an unrelated edit elsewhere in a file never spuriously reopens an
# accepted pair. Each entry is ONE group: a finding passes only if its whole member
# set falls inside a SINGLE baselined group. A-170 replaced the former flat set of
# pairs with these groups because the flat shape accepted any duplication BETWEEN
# two already-listed functions, and widening to tests grew that set from 16 pairs to
# 80 — turning a small hole into a large one.

# Every entry below is REAL duplication carrying a stated reason for still being
# here — see test_baseline_holds_no_stale_group, which mechanises that meaning by
# failing the moment an entry's duplication is gone.
_COPY_PASTE_BASELINE = frozenset(
    {
        # Habitat's engine raises the automated alert, Masar's whitelisted one-tap
        # raises the manual one; one rule ("HR Manager, else System Manager"), so the
        # home is apex_core/utils/ — the shared kernel BOTH already import. Owning
        # salis/ is NOT the blocker recorded here before: with habitat/ out of write
        # scope, promoting the body only leaves habitat duplicating the NEW shared
        # copy. The blocker is write access to temporary_worker_engine.py, where the
        # remaining fix is an import plus a one-line call.
        frozenset(
            {
                ("habitat/temporary_worker_engine.py", "_hr_recipients"),
                ("salis/api/masar.py", "_hr_notify_recipients"),
            }
        ),
        # The ONLY entry retained on merit rather than scope. Patches are frozen
        # history: both have already run on every installed site and are skipped
        # forever after (patch log), so promoting a shared helper changes no runtime
        # behaviour anywhere while risking a re-run on a fresh install. Duplication
        # is the correct trade for a one-shot script; do not "fix" this.
        frozenset(
            {
                ("patches/v1_x/seed_demo_role_logins.py", "_get_or_create"),
                ("patches/v1_x/seed_masar_demo_movement.py", "_get_or_create"),
            }
        ),
    }
)


class TestCopyPastedFunctionBodies(unittest.TestCase):
    def test_detector_flags_identical_bodies_ignores_short_ones(self):
        # [#a056t2]
        src = (
            "def a():\n    x = 1\n    y = 2\n    return x + y\n\n"
            "def b():\n    x = 1\n    y = 2\n    return x + y\n\n"
            "def c():\n    return 1\n"
        )
        tree = ast.parse(src)
        funcs = {fn.name: fn for fn in _all_funcs(tree)}
        self.assertEqual(_body_signature(funcs["a"]), _body_signature(funcs["b"]))
        self.assertLess(len(_non_docstring_body(funcs["c"])), 3, "short stub must not qualify")

    def test_signature_matches_a_body_whose_locals_are_renamed(self):
        # [#a185al] The escaped shape: one body pasted with every local relabelled,
        # including the self/doc parameter split the detached-controller style makes.
        original = (
            "def a(self):\n"
            "    rows = {}\n"
            "    for row in read():\n"
            "        rows[row[0]] = row[1]\n"
            "    return rows\n"
        )
        pasted = (
            "def b(doc):\n"
            "    out = {}\n"
            "    for r in read():\n"
            "        out[r[0]] = r[1]\n"
            "    return out\n"
        )
        self.assertEqual(_signature_of(original, "a"), _signature_of(pasted, "b"))

    def test_signature_keeps_load_bearing_names(self):
        # [#a185lb] Each variant differs from the base in exactly ONE name class that
        # carries meaning; abstracting any of them would merge different functions.
        base = 'def f(doc):\n    v = doc.status\n    log(v, "Open", safe=True)\n    return v\n'
        variants = {
            "field name": 'def f(doc):\n    v = doc.state\n    log(v, "Open", safe=True)\n    return v\n',
            "free name": 'def f(doc):\n    v = doc.status\n    warn(v, "Open", safe=True)\n    return v\n',
            "literal": 'def f(doc):\n    v = doc.status\n    log(v, "Closed", safe=True)\n    return v\n',
            "keyword name": 'def f(doc):\n    v = doc.status\n    log(v, "Open", strict=True)\n    return v\n',
        }
        for label, src in variants.items():
            self.assertNotEqual(
                _signature_of(base, "f"),
                _signature_of(src, "f"),
                f"{label} is meaning, not a binding artefact — it must stay significant",
            )

    def test_signature_keeps_import_bound_names(self):
        # [#a185ib] `from m import alpha` binds alpha, but the name IS the symbol.
        first = "def f():\n    from m import alpha\n    v = alpha()\n    return v\n"
        second = "def f():\n    from m import beta\n    v = beta()\n    return v\n"
        self.assertNotEqual(_signature_of(first, "f"), _signature_of(second, "f"))

    def test_signature_numbers_locals_by_binding_order_not_use_order(self):
        # [#a185bo] Two parameters, one used: numbering by USE order would place
        # whichever argument is read first at index 0 and call these one function.
        first = "def f(a, b):\n    x = load(a)\n    check(x)\n    return x\n"
        second = "def f(a, b):\n    x = load(b)\n    check(x)\n    return x\n"
        self.assertNotEqual(_signature_of(first, "f"), _signature_of(second, "f"))

    def test_signature_stays_order_sensitive(self):
        # [#a185os] Statement reordering was measured and REJECTED: an
        # order-insensitive body signature found zero duplication the alpha-renamed
        # one did not, at HEAD and at two earlier revisions, while calling these two
        # bodies equal — a save before the field is set is a different function.
        write_then_save = 'def f(doc):\n    doc.total = 1\n    doc.save()\n    return doc.total\n'
        save_then_write = 'def f(doc):\n    doc.save()\n    doc.total = 1\n    return doc.total\n'
        self.assertNotEqual(
            _signature_of(write_then_save, "f"), _signature_of(save_then_write, "f")
        )

    def test_unittest_dispatch_exemption_cannot_hide_a_parameterised_helper(self):
        # [#a170t2] The exemption's two halves: an idiomatic zero-arg setUp/test
        # method is skipped, but a helper is NOT exempt just for wearing the name.
        src = (
            "class T:\n"
            "    def setUp(self):\n        pass\n"
            "    def test_thing(self):\n        pass\n"
            "    def test_make_building(self, site, rooms):\n        pass\n"
            "    def _make_building(self, site):\n        pass\n"
        )
        by_name = {fn.name: fn for fn in _all_funcs(ast.parse(src))}
        self.assertTrue(_is_unittest_dispatched(by_name["setUp"]))
        self.assertTrue(_is_unittest_dispatched(by_name["test_thing"]))
        self.assertFalse(
            _is_unittest_dispatched(by_name["test_make_building"]),
            "a test_-named function taking fixture arguments must stay in the scan",
        )
        self.assertFalse(_is_unittest_dispatched(by_name["_make_building"]))

    def test_baseline_is_group_keyed_not_a_flat_pair_set(self):
        # [#a170t3] Guards the containment shape: a cross-group union must not pass.
        self.assertTrue(all(isinstance(g, frozenset) for g in _COPY_PASTE_BASELINE))
        groups = [g for g in _COPY_PASTE_BASELINE if len(g) >= 2]
        self.assertGreaterEqual(len(groups), 2, "need two groups to test cross-group leakage")
        smuggled = {sorted(groups[0])[0], sorted(groups[1])[0]}
        self.assertFalse(
            any(smuggled <= g for g in _COPY_PASTE_BASELINE),
            "one member from each of two different baselined groups must NOT be accepted",
        )

    def test_baseline_holds_no_stale_group(self):
        # [#a176st] The ratchet's other direction. test_no_new_copy_pasted_function_body
        # only stops the frozen set GROWING; nothing stopped it keeping an entry whose
        # duplication had already been removed, so "listed" would have degraded into
        # "listed once, for reasons nobody can still check". Failing on a stale entry
        # forces the de-duplication and the shrink into the SAME commit and makes
        # membership mean exactly one thing: real, still-live, deliberately retained.
        live = [{(rel, name) for rel, _lineno, name in locs}
                for locs in _copy_pasted_groups().values()]
        stale = sorted(
            sorted(group) for group in _COPY_PASTE_BASELINE
            if not any(keys <= group for keys in live)
        )
        self.assertEqual(
            stale,
            [],
            "Baselined copy-paste group(s) no longer duplicated — the debt is gone, so "
            "delete the entry from _COPY_PASTE_BASELINE in the commit that fixed it:\n"
            + "\n".join(f"  {g}" for g in stale),
        )

    def test_no_new_copy_pasted_function_body(self):
        groups = _copy_pasted_groups()
        offenders = {}
        for sig, locs in groups.items():
            keys = {(rel, name) for rel, _lineno, name in locs}
            # Must fit inside ONE baselined group: accepting a union across groups
            # would let two already-listed helpers become copies of each other.
            if not any(keys <= group for group in _COPY_PASTE_BASELINE):
                offenders[sig] = locs
        self.assertEqual(
            offenders,
            {},
            "New copy-pasted function body detected (identical statements, operators "
            "and literals — comments/names/docstrings don't matter). Extract a shared "
            "helper instead of duplicating the block:\n"
            + "\n".join(
                "  " + " == ".join(f"{r}:{ln}:{n}" for r, ln, n in locs)
                for locs in offenders.values()
            ),
        )


# 3. Orphan DocTypes (module JSON with no wiring)

def _module_registry():
    with open(MODULES_TXT, encoding="utf-8") as fh:
        return {ln.strip() for ln in fh if ln.strip()}


def _doctype_jsons():
    """(path, data) for every doctype/<x>/<x>.json anywhere under apex/ that is
    itself a DocType definition (not a sibling file such as a *_dashboard.json)."""
    out = []
    pattern = os.path.join(APP_ROOT, "**", "doctype", "*", "*.json")
    for path in sorted(glob.glob(pattern, recursive=True)):
        if "node_modules" in path:
            continue
        base = os.path.splitext(os.path.basename(path))[0]
        if os.path.basename(os.path.dirname(path)) != base:
            continue
        with open(path, encoding="utf-8") as fh:
            try:
                data = json.load(fh)
            except json.JSONDecodeError:
                continue
        if isinstance(data, dict) and data.get("doctype") == "DocType":
            out.append((path, data))
    return out


def _orphan_doctypes():
    modules = _module_registry()
    offenders = []
    for path, data in _doctype_jsons():
        declared = data.get("module")
        rel = _rel(path)
        module_dir = rel.split(os.sep)[0]
        if declared not in modules:
            offenders.append(
                f"{rel}: module {declared!r} is not registered in modules.txt {sorted(modules)}"
            )
        elif module_dir != _scrub(declared):
            offenders.append(
                f"{rel}: declares module {declared!r} (expected folder "
                f"{_scrub(declared)!r}) but lives under {module_dir!r}"
            )
    return offenders


class TestOrphanDocTypes(unittest.TestCase):
    def test_scan_finds_doctypes(self):
        names = {data.get("name") for _path, data in _doctype_jsons()}
        self.assertIn("Building", names, "DocType scan found nothing — parser broke")

    def test_detector_flags_module_not_in_registry(self):
        # [#a056t3]
        modules = _module_registry()
        self.assertNotIn("Retired Module", modules)

    def test_no_orphan_doctype_module(self):
        offenders = _orphan_doctypes()
        self.assertEqual(
            offenders,
            [],
            "DocType JSON declares (or sits under) a module that is not a registered "
            "Frappe module — Frappe will never load it: add the module to modules.txt, "
            "fix the JSON's `module` field, or move the DocType to its real module "
            "folder:\n" + "\n".join(f"  {o}" for o in offenders),
        )


# 4. Dead production modules (zero importers / zero wiring)

_DOTTED_RE = re.compile(r"\bapex(?:_habitat)?(?:\.[A-Za-z_][A-Za-z0-9_]*)+")
_CONVENTION_DIRS = {"doctype", "report", "page", "web_form", "notification"}


def _add_with_ancestors(refs, dotted):
    parts = dotted.split(".")
    for i in range(1, len(parts) + 1):
        refs.add(".".join(parts[:i]))


def _collect_import_references():
    """Every dotted module path (+ its ancestors) imported anywhere under apex/
    (production AND tests — a file used only by a test fixture is not dead)."""
    refs = set()
    for path in _scanned_py_files():
        tree = _parse(path)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    _add_with_ancestors(refs, alias.name)
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                _add_with_ancestors(refs, node.module)
                for alias in node.names:
                    _add_with_ancestors(refs, f"{node.module}.{alias.name}")
    return refs


def _collect_text_references():
    """Every dotted apex(_habitat)? path mentioned as a STRING anywhere under
    apex/ (hooks.py doc_events/scheduler_events, patches.txt, and any JSON's
    Custom Number Card `method` / Dashboard Chart `source` / Notification
    `method` wiring) — a blunt but conservative net that covers every dynamic
    Frappe wiring convention without hand-listing each one."""
    refs = set()
    texts = [PATCHES_TXT]
    texts += _scanned_py_files()
    texts += glob.glob(os.path.join(APP_ROOT, "**", "*.json"), recursive=True)
    for path in texts:
        if "node_modules" in path:
            continue
        try:
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
        except (OSError, UnicodeDecodeError):
            continue
        for m in _DOTTED_RE.finditer(text):
            _add_with_ancestors(refs, m.group(0))
    return refs


def _is_convention_loaded(path):
    """Frappe loads these by NAME/PATH convention, never a Python import:
    <module>/{doctype,report,page,web_form,notification}/<slug>/<slug>.py, the
    <module>/doctype/<slug>/<slug>_dashboard.py form "Connections" module (loaded
    via load_doctype_module(..., suffix="_dashboard")), or any apex/www/**.py page
    controller."""
    rel = _rel(path)
    parts = rel.split(os.sep)
    if parts[0] == "www":
        return True
    base = os.path.splitext(os.path.basename(path))[0]
    parent = os.path.basename(os.path.dirname(path))
    grandparent = os.path.basename(os.path.dirname(os.path.dirname(path)))
    if base == parent and grandparent in _CONVENTION_DIRS:
        return True
    # Frappe form dashboard: <module>/doctype/<slug>/<slug>_dashboard.py — loaded
    # by convention (suffix="_dashboard"), never imported by dotted path.
    return grandparent == "doctype" and base == parent + "_dashboard"


def _has_whitelisted_endpoint(tree):
    """True if the module binds >= 1 ``@frappe.whitelist(...)`` function — that
    makes it HTTP-reachable by dotted path with zero Python-side imports."""
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            target = dec.func if isinstance(dec, ast.Call) else dec
            if isinstance(target, ast.Attribute) and target.attr == "whitelist":
                return True
            if isinstance(target, ast.Name) and target.id == "whitelist":
                return True
    return False


def _dead_production_modules():
    refs = _collect_import_references() | _collect_text_references()
    offenders = []
    for path in _production_py_files():
        if os.path.basename(path) in ("__init__.py", "hooks.py"):
            continue
        if _is_convention_loaded(path):
            continue
        tree = _parse(path)
        if tree is None:
            continue
        if _has_whitelisted_endpoint(tree):
            continue
        if _file_dotted_path(path) not in refs:
            offenders.append(_rel(path))
    return offenders


# [#a056b3] Baseline for production files not reachable by any reference this
# scan can see. Now EMPTY: the original three entries were deleted, so any
# zero-importer file fails. Keep it empty — delete the file or wire it up.
_DEAD_FILE_BASELINE = frozenset()


class TestDeadProductionModules(unittest.TestCase):
    def test_convention_loader_recognises_a_known_controller(self):
        # [#a056t4]
        known = os.path.join(APP_ROOT, "habitat", "doctype", "building", "building.py")
        self.assertTrue(os.path.exists(known), "fixture path drifted — update this test")
        self.assertTrue(_is_convention_loaded(known))

    def test_convention_loader_rejects_a_non_convention_path(self):
        self.assertFalse(_is_convention_loaded(os.path.join(APP_ROOT, "hooks.py")))

    def test_no_new_dead_production_module(self):
        offenders = set(_dead_production_modules())
        new = offenders - _DEAD_FILE_BASELINE
        self.assertEqual(
            new,
            set(),
            "New unreferenced production .py file (no importer, no hooks.py/JSON/"
            "patches.txt wiring, not a Frappe-convention controller, no whitelisted "
            "endpoint). Read-before-write: either wire it up, delete it, or if it is "
            "a real Frappe entrypoint this scan doesn't recognise, extend "
            "_is_convention_loaded / _collect_text_references instead of ignoring it:\n"
            + "\n".join(f"  {f}" for f in sorted(new)),
        )


# 4b. Dead production FUNCTIONS (a live file's unreferenced module-level def)

# [#a246df] Reachability rules and why the scan universe is wider than check 4's:
# see the module docstring, item 4b.

_WIRING_TEXT_EXTS = ("*.json", "*.js", "*.html", "*.txt", "*.md")


def _wiring_text_files():
    """Every non-Python file that can name a Python function by dotted path.

    Includes the published docs, which are a REAL wiring surface: three entry
    points in patches/v2_0/app_identity_cutover.py have no Python caller and
    exist only to be run as `bench --site <site> execute apex....<fn>` per
    docs/administration/identity-upgrade.md. Drop docs from this universe and the guard
    reports live, documented operator commands as dead code.
    """
    paths = [PATCHES_TXT]
    for pattern in _WIRING_TEXT_EXTS:
        paths += glob.glob(os.path.join(APP_ROOT, "**", pattern), recursive=True)
        paths += glob.glob(os.path.join(REPO_ROOT, "docs", "**", pattern), recursive=True)
    paths += glob.glob(os.path.join(REPO_ROOT, "*.md"))
    return [p for p in paths if "node_modules" not in p]


def _dotted_tails(text, names):
    """Add every segment of every dotted apex path in ``text``.

    The whole path is kept, unlike _add_with_ancestors which throws the function
    tail away — that tail is exactly what this check needs.
    """
    for match in _DOTTED_RE.finditer(text):
        names.update(match.group(0).split("."))


def _all_exported_names(tree):
    """Names listed in a module's ``__all__`` (a barrel's re-export contract)."""
    exported = set()
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets):
            continue
        if isinstance(node.value, (ast.List, ast.Tuple, ast.Set)):
            for element in node.value.elts:
                if isinstance(element, ast.Constant) and isinstance(element.value, str):
                    exported.add(element.value)
    return exported


def _referenced_function_names():
    """Every identifier this app mentions in a position that could reach a def."""
    names = set()
    for path in _scanned_py_files():
        tree = _parse(path)
        if tree is None:
            continue
        names |= _all_exported_names(tree)
        for node in ast.walk(tree):
            # (a) a bare call/reference, and the alias half of any import —
            # `from x import y` is how a re-exported name enters a barrel.
            if isinstance(node, ast.Name):
                names.add(node.id)
            elif isinstance(node, ast.Attribute):
                names.add(node.attr)
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    names.add(alias.name)
                    if alias.asname:
                        names.add(alias.asname)
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                # (c) dotted wiring written as a Python string literal
                _dotted_tails(node.value, names)
    for path in _wiring_text_files():
        try:
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
        except (OSError, UnicodeDecodeError):
            continue
        _dotted_tails(text, names)
    return names


def _is_whitelisted(fn):
    """(d) @frappe.whitelist on THIS def — per-function, not per-module."""
    for dec in fn.decorator_list:
        target = dec.func if isinstance(dec, ast.Call) else dec
        if isinstance(target, ast.Attribute) and target.attr == "whitelist":
            return True
        if isinstance(target, ast.Name) and target.id == "whitelist":
            return True
    return False


def _dead_production_functions():
    """[(rel_path, func_name)] for module-level defs nothing can reach."""
    referenced = _referenced_function_names()
    offenders = []
    for path in _production_py_files():
        if os.path.basename(path) == "hooks.py":
            continue
        tree = _parse(path)
        if tree is None:
            continue
        for fn in _module_level_funcs(tree):
            if fn.name in DISPATCH_NAMES or _is_whitelisted(fn):
                continue
            if fn.name in referenced:
                continue
            offenders.append((_rel(path), fn.name))
    return offenders


# [#a246fb] Seeded with 8 pre-existing dead defs so this check could land green,
# and now EMPTY — every one was deleted rather than re-wired (see the module
# docstring for what each was). So this check is a plain gate again: any dead def
# a change introduces fails it outright. Do not re-open the set to silence a new
# finding; delete the function or wire it up. If an entry ever is added back,
# test_baseline_holds_no_revived_function forces its removal once it stops
# being dead.
_DEAD_FUNCTION_BASELINE = frozenset()


class TestDeadProductionFunctions(unittest.TestCase):
    def test_baseline_holds_no_revived_function(self):
        """A baselined def that is no longer dead must lose its entry."""
        still_dead = set(_dead_production_functions())
        revived = sorted(_DEAD_FUNCTION_BASELINE - still_dead)
        self.assertEqual(
            revived,
            [],
            "These functions are no longer dead (deleted, or now referenced). "
            "Drop them from _DEAD_FUNCTION_BASELINE in the same commit:\n"
            + "\n".join(f"  {p}: {n}" for p, n in revived),
        )

    # Both directions pinned: it must NAME a dead def and STAY SILENT on
    # name-only wiring — a guard that flags hook targets gets switched off.

    def test_a_plain_unreferenced_name_is_not_a_reference(self):
        names = _referenced_function_names()
        self.assertNotIn("zzz_apex_guard_probe_never_defined", names)

    def test_dotted_path_string_counts_its_function_tail(self):
        # hooks.py / Number Card `method` / frappe.enqueue(...) shape
        names = set()
        _dotted_tails('"apex.habitat.tasks.cost.daily_accommodation_cost_allocation"', names)
        self.assertIn("daily_accommodation_cost_allocation", names)
        self.assertIn("cost", names)

    def test_dotted_path_tail_survives_unlike_the_module_scan(self):
        # _add_with_ancestors (check 4) throws the tail away; this check needs it.
        module_refs = set()
        _add_with_ancestors(module_refs, "apex.a.b.some_function")
        self.assertNotIn("some_function", module_refs)
        function_refs = set()
        _dotted_tails("apex.a.b.some_function", function_refs)
        self.assertIn("some_function", function_refs)

    def test_all_export_counts_as_a_reference(self):
        tree = ast.parse('__all__ = ["get_workshop_overstay_count", "_raise_alert"]\n')
        self.assertEqual(
            _all_exported_names(tree),
            {"get_workshop_overstay_count", "_raise_alert"},
        )

    def test_whitelisted_function_is_exempt(self):
        for source in (
            "@frappe.whitelist()\ndef endpoint():\n    pass\n",
            '@frappe.whitelist(methods=["POST"])\ndef endpoint():\n    pass\n',
            "@whitelist\ndef endpoint():\n    pass\n",
        ):
            fn = ast.parse(source).body[0]
            self.assertTrue(_is_whitelisted(fn), source)

    def test_undecorated_function_is_not_exempt(self):
        fn = ast.parse("def endpoint():\n    pass\n").body[0]
        self.assertFalse(_is_whitelisted(fn))

    def test_documented_bench_execute_entrypoints_are_reachable(self):
        # patches/v2_0/app_identity_cutover.py's three entry points have no
        # Python caller; docs/administration/identity-upgrade.md is their only wiring.
        names = _referenced_function_names()
        for fn_name in ("preview_registry", "diagnose", "cutover"):
            self.assertIn(fn_name, names, f"{fn_name} lost its docs reference")
        dead = {n for _, n in _dead_production_functions()}
        self.assertEqual(dead & {"preview_registry", "diagnose", "cutover"}, set())

    def test_docs_are_in_the_reference_universe(self):
        upgrade_doc = os.path.join(REPO_ROOT, "docs", "administration", "identity-upgrade.md")
        self.assertTrue(os.path.exists(upgrade_doc), "fixture path drifted")
        self.assertIn(upgrade_doc, _wiring_text_files())

    def test_no_new_dead_production_function(self):
        offenders = set(_dead_production_functions())
        new = offenders - _DEAD_FUNCTION_BASELINE
        self.assertEqual(
            new,
            set(),
            "Module-level function with no reachable reference (no Python caller, "
            "no __all__ export, no dotted path in any .py/.json/.js/.html/"
            "patches.txt, no @frappe.whitelist, not a Frappe dispatch name). "
            "Delete it or wire it up; if it IS reachable by a mechanism this scan "
            "cannot see, teach _referenced_function_names about that mechanism "
            "rather than baselining it:\n"
            + "\n".join(f"  {p}: {n}" for p, n in sorted(new)),
        )


# 5. Native-primitive bypass (custom code where a Frappe primitive exists)

# [#a056np] Kept deliberately SHORT: each entry names a stdlib primitive with NO
# legitimate exception found in this repo today (see module docstring for why
# hashlib is intentionally NOT here). Add "# native-ok: <reason>" on the same
# line to justify a new, reviewed exception instead of widening the pattern.
_NATIVE_BYPASS_PATTERNS = (
    (
        "smtplib",
        "frappe.sendmail() (queued, templated, retried) instead of a raw SMTP client",
        re.compile(r"^\s*(import\s+smtplib\b|from\s+smtplib\b)"),
    ),
    (
        "uuid",
        "frappe.generate_hash(length=n) instead of the stdlib uuid module",
        re.compile(r"^\s*(import\s+uuid\b|from\s+uuid\b)"),
    ),
)


def _native_bypass_offenders():
    offenders = []
    for path in _production_py_files():
        with open(path, encoding="utf-8") as fh:
            lines = fh.readlines()
        for lineno, line in enumerate(lines, 1):
            if "native-ok" in line:
                continue
            for name, hint, pattern in _NATIVE_BYPASS_PATTERNS:
                if pattern.search(line):
                    offenders.append(f"{_rel(path)}:{lineno}: {name} — use {hint}")
    return offenders


class TestNativePrimitiveBypass(unittest.TestCase):
    def test_detector_flags_import_ignores_justified_line(self):
        # [#a056t5]
        _name, _hint, pattern = _NATIVE_BYPASS_PATTERNS[0]
        self.assertTrue(pattern.search("import smtplib"))
        self.assertTrue(pattern.search("    from smtplib import SMTP"))
        self.assertFalse(pattern.search("# see smtplib docs for context"))

    def test_no_unjustified_native_primitive_bypass(self):
        offenders = _native_bypass_offenders()
        self.assertEqual(
            offenders,
            [],
            "Custom code reimplements a native Frappe primitive with no justification. "
            "Use the named native primitive, or add `# native-ok: <reason>` on the same "
            "line if this call site is a reviewed, genuine exception:\n"
            + "\n".join(f"  {o}" for o in offenders),
        )


if __name__ == "__main__":
    unittest.main()
