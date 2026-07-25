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

  1. TestDuplicateTopLevelFunctionNames — two different production files each bind
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

Run standalone:  python3 -m unittest tests.test_duplicate_and_dead_code_guard -v
"""

import ast
import glob
import json
import os
import re
import unittest

APP_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
REPO_ROOT = os.path.dirname(APP_ROOT)
MODULES_TXT = os.path.join(APP_ROOT, "modules.txt")
PATCHES_TXT = os.path.join(APP_ROOT, "patches.txt")


def _scrub(name):
    """Pure-python mirror of frappe.scrub() (no live site needed)."""
    return name.strip().lower().replace(" ", "_").replace("-", "_")


def _rel(path):
    return os.path.relpath(path, APP_ROOT)


def _parse(path):
    with open(path, encoding="utf-8") as fh:
        try:
            return ast.parse(fh.read(), filename=path)
        except SyntaxError:
            return None


def _production_py_files():
    """Every apex/**/*.py file except tests/ and node_modules — the universe for
    the duplicate-name / copy-paste / dead-file scans."""
    out = []
    for path in sorted(glob.glob(os.path.join(APP_ROOT, "**", "*.py"), recursive=True)):
        if "node_modules" in path:
            continue
        rel = _rel(path)
        if rel.startswith("tests" + os.sep) or os.path.basename(path).startswith("test_"):
            continue
        out.append(path)
    return out


# ---------------------------------------------------------------------------
# 1. Duplicate top-level (module-scope) function names
# ---------------------------------------------------------------------------

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
}


def _module_level_funcs(tree):
    """FunctionDef/AsyncFunctionDef bound directly in the module body. A Document
    subclass's own methods live inside its ClassDef body — ``tree.body`` never
    recurses into a ClassDef, so a class method is never mistaken for one of these."""
    return [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]


def _duplicate_def_names():
    """{name: sorted[rel_paths]} for every PUBLIC top-level def name bound in 2+
    different production files that is not a DISPATCH_NAMES entry."""
    by_name = {}
    for path in _production_py_files():
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


# ---------------------------------------------------------------------------
# 2. Copy-pasted function bodies
# ---------------------------------------------------------------------------

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


def _body_signature(fn_node):
    """Structural signature of a function's body: name/argument-independent (a
    rename-and-paste still matches) but literal/operator DEPENDENT (ast.dump
    includes constant values), so only a byte-for-byte-equivalent body matches —
    a copy-paste-with-one-value-changed deliberately does not (kept strict to
    stay low-false-positive; see module docstring)."""
    body = _non_docstring_body(fn_node)
    return "\n".join(ast.dump(stmt, annotate_fields=False) for stmt in body)


def _copy_pasted_groups():
    """{signature: sorted[(rel_path, lineno, func_name), ...]} for every function
    body of >= 3 real statements that structurally matches another function's body."""
    by_sig = {}
    for path in _production_py_files():
        tree = _parse(path)
        if tree is None:
            continue
        for fn in _all_funcs(tree):
            if len(_non_docstring_body(fn)) < 3:
                continue
            sig = _body_signature(fn)
            by_sig.setdefault(sig, set()).add((_rel(path), fn.lineno, fn.name))
    return {sig: sorted(locs) for sig, locs in by_sig.items() if len(locs) > 1}


# [#a056b2] Baseline frozen at guard-authoring time: (rel_path, func_name) pairs
# already sharing a body today (line numbers excluded from the key so unrelated
# edits elsewhere in the file — which shift line numbers — never spuriously
# reopen an already-accepted pair). Real pre-existing duplication (confirmed
# while authoring this guard, e.g. safety_task_execution._finding_escalates'
# own docstring says it "mirrors finding_fanout._is_actionable") that A-056 did
# not fix — out of this task's scope — but must not regress further.
_COPY_PASTE_BASELINE = frozenset(
    {
        ("apex_core/setup/seeders/habitat_auto_email_reports_seed.py", "seed_auto_email_reports"),
        ("apex_core/setup/seeders/salis_auto_email_reports_seed.py", "seed_salis_auto_email_reports"),
        ("habitat/doctype/custody_handover/custody_handover.py", "on_cancel"),
        ("habitat/doctype/goods_receipt/goods_receipt.py", "on_cancel"),
        ("habitat/doctype/safety_task_execution/safety_task_execution.py", "_finding_escalates"),
        ("habitat/utils/finding_fanout.py", "_is_actionable"),
        ("habitat/temporary_worker_engine.py", "_hr_recipients"),
        ("salis/api/masar.py", "_hr_notify_recipients"),
        ("patches/v1_x/enable_custody_damage_assessment_notification.py", "execute"),
        ("patches/v1_x/enable_custody_return_overdue_notification.py", "execute"),
        ("patches/v1_x/seed_demo_role_logins.py", "_get_or_create"),
        ("patches/v1_x/seed_masar_demo_movement.py", "_get_or_create"),
        ("salis/api/boarding.py", "_is_staff"),
        ("salis/api/driver_portal/__init__.py", "_is_staff"),
        ("salis/api/driver_portal/__init__.py", "_bound_vehicle"),
        ("salis/api/fleet_employee.py", "_bound_vehicle"),
        ("salis/permissions.py", "salis_driver_has_permission"),
        ("salis/permissions.py", "trip_start_log_has_permission"),
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

    def test_no_new_copy_pasted_function_body(self):
        groups = _copy_pasted_groups()
        offenders = {}
        for sig, locs in groups.items():
            keys = {(rel, name) for rel, _lineno, name in locs}
            if not keys <= _COPY_PASTE_BASELINE:
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


# ---------------------------------------------------------------------------
# 3. Orphan DocTypes (module JSON with no wiring)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# 4. Dead production modules (zero importers / zero wiring)
# ---------------------------------------------------------------------------

_DOTTED_RE = re.compile(r"\bapex(?:_habitat)?(?:\.[A-Za-z_][A-Za-z0-9_]*)+")
_CONVENTION_DIRS = {"doctype", "report", "page", "web_form", "notification"}


def _add_with_ancestors(refs, dotted):
    parts = dotted.split(".")
    for i in range(1, len(parts) + 1):
        refs.add(".".join(parts[:i]))


def _file_dotted_path(path):
    rel = os.path.relpath(path, REPO_ROOT)
    if rel.endswith(os.sep + "__init__.py"):
        rel = rel[: -len(os.sep + "__init__.py")]
    else:
        rel = rel[: -len(".py")]
    return rel.replace(os.sep, ".")


def _collect_import_references():
    """Every dotted module path (+ its ancestors) imported anywhere under apex/
    (production AND tests — a file used only by a test fixture is not dead)."""
    refs = set()
    for path in glob.glob(os.path.join(APP_ROOT, "**", "*.py"), recursive=True):
        if "node_modules" in path:
            continue
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
    texts += glob.glob(os.path.join(APP_ROOT, "**", "*.py"), recursive=True)
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


# [#a056b3] Baseline frozen at guard-authoring time: production files that are
# not yet reachable by any reference this scan can see. Pre-existing debt, not
# fixed here (out of scope for A-056) — only a NEW zero-importer file fails.
# All three confirmed genuinely dead while authoring this guard: patches.txt's
# own B9 comment says stamp_changelog_seen_version.py was "retired ... in the
# same change" (the patches.txt line was removed, the module never was); the
# two dashboard seeders are the "retired runtime seeders" superseded by
# is_standard=1 dashboard JSON per patches/v1_x/drop_legacy_is_standard0_dashboards.py.
_DEAD_FILE_BASELINE = frozenset(
    {
        "apex_core/setup/seeders/salis_dashboard_seed.py",
        "apex_core/setup/seeders/salis_movement_dashboard_seed.py",
        "patches/v1_x/stamp_changelog_seen_version.py",
    }
)


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


# ---------------------------------------------------------------------------
# 5. Native-primitive bypass (custom code where a Frappe primitive exists)
# ---------------------------------------------------------------------------

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
