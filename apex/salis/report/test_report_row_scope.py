# Copyright (c) 2026, AFMCO and contributors
"""A-217 — a Script Report over a row-scoped DocType that forgets to re-apply the scope.

``permission_query_conditions`` is a LIST-view mechanism. ``frappe/model/db_query.py``
composes the registered fragment into the WHERE clause it builds, so every desk list,
link search and ``frappe.get_list`` inherits the row boundary for free. A Script Report
inherits nothing: ``frappe/desk/query_report.py`` checks
``frappe.has_permission(ref_doctype, "report")`` ONCE at :47 and then executes the
module's own ``execute()``, whose queries are ``frappe.get_all`` (which forces
``ignore_permissions=True``) or raw SQL. Neither goes anywhere near the registered
fragment. The permission check answers "may this role open this report", never "which
rows may it see".

So for every DocType this app scopes, the scope survives inside a report ONLY because
the report re-applies it in Python. That is a convention, and until this guard nothing
enforced it.

The concrete shape of the hazard: ``Resident Supervisor`` holds ``report`` on ``Housing
Assignment`` and is NOT in ``habitat/permissions.py`` ``HOUSING_UNSCOPED_ROLES``, so it
is genuinely building-scoped there. All three shipped Housing Assignment reports call
``report_building_scope`` before they query, which is why nothing leaks today. The next
Script Report over that DocType that omits the call hands that role every building's
resident records -- identity, placement, signature -- and no existing test notices.

WHAT IS ENUMERATED, AND FROM WHERE
The row-scoped DocTypes are read live out of ``hooks.permission_query_conditions``
(``scope_owning_modules``), never from a list written down here. A DocType scoped
tomorrow is covered the day its hook entry lands. The hook VALUE carries more than the fact of
scoping: ``apex.habitat.permissions.accommodation_assignment_query`` names the module
that OWNS that DocType's scope, so the guard also knows which vocabulary a report over
it must speak.

THE RULE: WHAT COUNTS AS "APPLIES THE SCOPE"
A report applies the scope when it CALLS a function defined in the permissions module
that ``hooks.py`` names for its ``ref_doctype``, from ``execute`` or from a function
``execute`` reaches in the same file.

The rule is deliberately not a list of blessed helper names. Five spellings are in use
across the report tree today (counts below are app-wide, so they include reports whose
ref is unscoped and which scope a JOINED master instead), and a name allowlist would have
to be extended for each -- the same class of defect as a hardcoded DocType list:

  1. ``permissions.report_building_scope(user)``      -- 11 habitat reports
  2. ``permissions.report_project_scope(user)``       -- 12 salis reports
  3. ``permissions.report_company_scope(user)``       -- 6 logistay reports
  4. ``permissions._building_is_unscoped(user)`` paired with ``_allowed_buildings(user)``
     -- 5 habitat reports that filter with the primitives instead of the wrapper
  5. ``report_maintenance_request_scope(user)``, imported by name rather than through a
     module alias -- 2 habitat reports, and the only owner/assignee scope in the set

All five are functions defined in an ``apex/*/permissions.py``, so all five satisfy one
rule, and a SIXTH helper added to that module tomorrow satisfies it without touching
this file. Both import spellings in use are resolved: ``from apex.salis import
permissions`` then ``permissions.f(...)``, and ``from apex.habitat.permissions import
f`` then ``f(...)``.

Two clauses make the rule hard to satisfy accidentally:

  * The call must resolve into the permissions module hooks.py names FOR THAT REF. A
    habitat report calling a salis helper does not scope a Building.
  * The call must sit in ``execute`` or in a function ``execute`` reaches through the
    file's own call graph. A scope call parked in a helper nothing runs buys no pass.
    All 32 clean reports satisfy this: 26 call it directly in ``execute``, 6 in a
    fetch helper that ``execute`` calls.

WHAT THIS STATIC CHECK CANNOT SEE, STATED RATHER THAN GUESSED
  * It proves the scope is RESOLVED, not that the resolved value is then USED. A report
    that calls ``report_building_scope`` and discards the result reads as clean here.
    That branch is what ``apex/tests/test_report_scope.py`` covers for the eight reports
    it drives, by asserting the filter actually handed to ``frappe.get_all``.
  * A Script Report whose code lives in the database ``report_script`` field instead of
    a module has no source to read. None ship today, and
    ``test_every_script_report_ships_a_python_module`` keeps it that way, so the skip
    can never quietly swallow a report.
  * The invariant is keyed on ``ref_doctype``, which is the DocType whose DocPerms gate
    the report and whose rows it is presumed to expose. A report whose ref is UNSCOPED
    but which joins a scoped DocType is outside it. Two ship: ``Checkout Pending
    Clearance`` (ref ``Housing Checkout``, joins Custody Issue / Custody Damage
    Assessment / Bed) and ``Transport Fulfilment SLA`` (ref ``Trip Fulfilment Ledger``,
    joins Transport Request). Neither was made a ratchet here: the only way to spot them
    statically is to scan for DocType names as string literals, and measured over this
    tree that scan returns 10 reports of which 8 are Link column ``options`` rather than
    queries -- a 20 percent precision detector is a guard that cries wolf, not a guard.
    They are recorded in the A-217 report as findings instead.

Run standalone:  python3 -m unittest apex.salis.report.test_report_row_scope -v
"""

import ast
import glob
import json
import os
import tempfile
import unittest
from collections import namedtuple

from apex.tests.shipped_doctypes import shipped_doctypes

_APP = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
_HOOKS = os.path.join(_APP, "hooks.py")
_REPORT_GLOB = os.path.join(_APP, "*", "report", "*", "*.json")

_FUNC = (ast.FunctionDef, ast.AsyncFunctionDef)
_ENTRYPOINT = "execute"

# Administrator short-circuits every permission check (frappe/permissions.py:107), so it
# is never the role a scope boundary is written for.
_ALWAYS_PERMITTED = frozenset({"Administrator"})

ScriptReport = namedtuple("ScriptReport", "ref roles source")

_MOVEMENT_KPI_AGGREGATE_ONLY = (
    "Emits no row from Dispatch Trip. The output is a fixed ten-entry KPI vocabulary -- "
    "a label, a scalar and a note per row -- produced by frappe.db.count and by sum()/"
    "avg() aggregates; no trip, request, driver, vehicle or worker identity reaches the "
    "result set, so there is no row for a scope filter to confine. The exemption is "
    "CONDITIONAL and re-checked on every run: the report's effective audience (its roles "
    "table intersected with the roles Dispatch Trip grants `report`) is Fleet Manager and "
    "Internal Auditor, and both are named in salis/permissions.py UNSCOPED_ROLES, so the "
    "ref is unscoped for every role that can open it and no boundary is crossed today. "
    "Add a project-scoped role to the roles table and "
    "test_every_exemption_audience_is_unscoped_for_its_ref fails -- the cross-project "
    "totals that role would then read are an aggregate disclosure, and the entry has to "
    "be resolved rather than re-frozen."
)

# Exact equality, like the sibling report baselines. Each entry is report -> (ref, reason);
# a new offender fails the build and a repaired one must be pruned, so the set only shrinks.
# An entry needs a WRITTEN reason (test_every_exemption_carries_a_written_reason) and its
# audience must still be unscoped for the ref (test_every_exemption_audience_is_unscoped_
# for_its_ref), so freezing an entry is never a permanent pardon.
SCOPE_EXEMPT_REPORTS = {
    "Movement KPI Summary": ("Dispatch Trip", _MOVEMENT_KPI_AGGREGATE_ONLY),
}


def _text(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def scope_owning_modules(hooks_path=_HOOKS):
    """``{DocType: dotted permissions module}`` from hooks.permission_query_conditions.

    The single enumeration point. Parsed rather than imported so the guard runs with no
    site and no frappe, and so a test can drive it against a mirrored hooks file to prove
    the enumeration is live rather than hardcoded.
    """
    for node in ast.walk(ast.parse(_text(hooks_path))):
        if not isinstance(node, ast.Assign):
            continue
        named = [t.id for t in node.targets if isinstance(t, ast.Name)]
        if "permission_query_conditions" in named:
            handlers = ast.literal_eval(node.value)
            return {dt: path.rsplit(".", 1)[0] for dt, path in handlers.items()}
    return {}


def permissions_exports(dotted):
    """Top-level function names a permissions module defines, or None when not on disk.

    This is the vocabulary a report over a DocType that module scopes must speak. Reading
    it off the module means a helper added there counts the day it lands.
    """
    if not dotted.startswith("apex."):
        return None
    path = os.path.join(_APP, *dotted.split(".")[1:]) + ".py"
    if not os.path.exists(path):
        return None
    return {node.name for node in ast.parse(_text(path)).body if isinstance(node, _FUNC)}


def scope_exempt_roles(dotted):
    """Roles a permissions module exempts from its own row scope.

    The union of every module-level set constant whose NAME carries "UNSCOPED"
    (``HOUSING_UNSCOPED_ROLES`` in habitat, ``UNSCOPED_ROLES`` in salis and logistay).
    Habitat's ``PRIVILEGED_ROLES``, which exempts the owner/assignee maintenance scope, is
    deliberately not matched: an exemption claimed against a Maintenance Request ref will
    find an empty intersection and be REFUSED, which is the direction a guard should fail.
    """
    roles = set()
    for node in ast.parse(_text(os.path.join(_APP, *dotted.split(".")[1:]) + ".py")).body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and "UNSCOPED" in target.id:
                try:
                    roles |= set(ast.literal_eval(node.value))
                except (ValueError, TypeError):
                    continue
    return roles


def shipped_script_reports():
    """``{report name: ScriptReport}`` for every Script Report in every module tree."""
    found = {}
    for path in sorted(glob.glob(_REPORT_GLOB)):
        try:
            record = json.loads(_text(path))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if not isinstance(record, dict) or record.get("doctype") != "Report":
            continue
        if record.get("report_type") != "Script Report" or not record.get("name"):
            continue
        folder = os.path.dirname(path)
        source = os.path.join(folder, os.path.basename(folder) + ".py")
        found[record["name"]] = ScriptReport(
            ref=record.get("ref_doctype"),
            roles=tuple(row["role"] for row in record.get("roles") or [] if row.get("role")),
            source=source if os.path.exists(source) else None,
        )
    return found


def _bound_scope_names(tree, dotted, exported):
    """``(module aliases, {local name: exported name})`` for the two import spellings."""
    aliases, direct = set(), {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for entry in node.names:
                if entry.name == dotted:
                    aliases.add(entry.asname or entry.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            for entry in node.names:
                if node.module + "." + entry.name == dotted:
                    aliases.add(entry.asname or entry.name)
                elif node.module == dotted and entry.name in exported:
                    direct[entry.asname or entry.name] = entry.name
    return aliases, direct


def _calls_scope(node, aliases, direct, exported):
    """True when anything under ``node`` calls a function of the bound permissions module."""
    for call in ast.walk(node):
        if not isinstance(call, ast.Call):
            continue
        func = call.func
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            if func.value.id in aliases and func.attr in exported:
                return True
        if isinstance(func, ast.Name) and func.id in direct:
            return True
    return False


def _local_call_graph(tree):
    """``{function: same-module functions it calls}`` for the file's top-level functions."""
    defined = {node.name: node for node in tree.body if isinstance(node, _FUNC)}
    graph = {}
    for name, node in defined.items():
        graph[name] = {
            call.func.id
            for call in ast.walk(node)
            if isinstance(call, ast.Call)
            and isinstance(call.func, ast.Name)
            and call.func.id in defined
        }
    return graph


def _reached_from(graph, entry):
    seen, pending = set(), [entry]
    while pending:
        current = pending.pop()
        if current in seen:
            continue
        seen.add(current)
        pending.extend(graph.get(current, ()))
    return seen


def applies_scope(source, dotted, exported):
    """True when the source resolves its ref's scope somewhere ``execute`` actually runs.

    Both clauses matter. Without the module check any function call would pass; without
    the reachability check a call parked in an unused helper would.
    """
    tree = ast.parse(source)
    aliases, direct = _bound_scope_names(tree, dotted, exported)
    if not aliases and not direct:
        return False
    holders = {
        node.name
        for node in tree.body
        if isinstance(node, _FUNC) and _calls_scope(node, aliases, direct, exported)
    }
    return bool(holders & _reached_from(_local_call_graph(tree), _ENTRYPOINT))


def unscoped_reports(reports, scoped):
    """``{report: ref_doctype}`` for every Script Report over a scoped ref that skips it.

    Pure over its inputs, so the planted proofs below drive it with synthetic reports and
    with a mirrored hooks enumeration instead of only whatever sits on disk today.
    """
    found = {}
    for name, report in sorted(reports.items()):
        dotted = scoped.get(report.ref)
        if dotted is None:
            continue
        exported = permissions_exports(dotted)
        # Both skips are asserted empty by TestNoReportIsSkippedUnseen, so neither can
        # hide an offender behind a shrug.
        if not exported or report.source is None:
            continue
        if not applies_scope(_text(report.source), dotted, exported):
            found[name] = report.ref
    return found


def report_grantees(ref, doctypes):
    """Roles holding a usable permlevel-0 ``report`` grant on ``ref``.

    Mirrors get_role_permissions: permlevel-0 only (frappe/permissions.py:284), and an
    if_owner-only grant cannot carry ``report`` because :307 rewrites every ptype outside
    ("select", "read") back to 0.
    """
    rows = (doctypes.get(ref) or {}).get("permissions") or []
    return {
        row["role"]
        for row in rows
        if row.get("role")
        and row.get("report")
        and not row.get("if_owner")
        and not int(row.get("permlevel") or 0)
    }


def report_audience(report, doctypes):
    """Roles that can actually open ``report``: its roles table narrowed by the ref grant.

    An empty roles table means the report is open to everyone the ref admits
    (frappe/boot.py:275-285). Custom Role can replace a roles table from the database
    without any file changing; the sibling test_workspace_report_runnable pins that
    door shut app-wide, so a file-level audience stays sufficient here.
    """
    grantees = report_grantees(report.ref, doctypes)
    declared = set(report.roles)
    return ((declared & grantees) if declared else grantees) - _ALWAYS_PERMITTED


def _mirror_hooks_with(entry, handler):
    """A copy of the real hooks.py with ONE extra permission_query_conditions entry.

    Text splice rather than a synthetic stub, so the mirror carries the whole live
    enumeration plus the new DocType and the proof is about a real addition.
    """
    lines = _text(_HOOKS).splitlines(keepends=True)
    for index, line in enumerate(lines):
        if line.startswith("permission_query_conditions = {"):
            lines.insert(index + 1, '    "{0}": "{1}",\n'.format(entry, handler))
            break
    else:
        raise AssertionError("permission_query_conditions is no longer a module-level dict")
    handle = tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8")
    handle.write("".join(lines))
    handle.close()
    return handle.name


class TestTheScanSeesTheWholeApp(unittest.TestCase):
    """A guard that silently scanned nothing would pass forever."""

    def setUp(self):
        self.scoped = scope_owning_modules()
        self.reports = shipped_script_reports()

    def test_the_hook_enumeration_is_read(self):
        self.assertGreaterEqual(
            len(self.scoped), 50, "permission_query_conditions parsed to too few entries"
        )
        self.assertIn("Housing Assignment", self.scoped, "the card's own ref is not enumerated")

    def test_every_scoping_module_resolves_to_a_readable_file(self):
        for dotted in sorted(set(self.scoped.values())):
            with self.subTest(module=dotted):
                exported = permissions_exports(dotted)
                self.assertTrue(exported, f"{dotted} exports no function the guard can see")

    def test_every_scoping_module_declares_a_non_empty_unscoped_set(self):
        """The exemption clause reads these; a rename must fail loudly, not widen it."""
        for dotted in sorted(set(self.scoped.values())):
            with self.subTest(module=dotted):
                self.assertTrue(
                    scope_exempt_roles(dotted),
                    f"{dotted} declares no *UNSCOPED* role set, so an exemption checked "
                    "against it would compare with the empty set and always fail closed. "
                    "If the constant was renamed, teach scope_exempt_roles the new shape.",
                )

    def test_the_report_glob_finds_every_module(self):
        modules = {os.path.relpath(p, _APP).split(os.sep)[0] for p in glob.glob(_REPORT_GLOB)}
        self.assertEqual(
            modules,
            {"habitat", "logistay", "salis"},
            "the report glob no longer covers every module that ships a report",
        )

    def test_the_in_scope_population_is_plausible(self):
        in_scope = [r for r in self.reports.values() if r.ref in self.scoped]
        self.assertGreaterEqual(
            len(in_scope),
            30,
            f"only {len(in_scope)} Script Reports over a scoped ref — the scan broke",
        )


class TestNoReportIsSkippedUnseen(unittest.TestCase):
    """The two skips in ``unscoped_reports`` must stay empty, or green means nothing."""

    def setUp(self):
        self.scoped = scope_owning_modules()
        self.reports = shipped_script_reports()

    def test_every_script_report_ships_a_python_module(self):
        sourceless = sorted(n for n, r in self.reports.items() if r.source is None)
        self.assertEqual(
            sourceless,
            [],
            "Script Report(s) with no <folder>.py beside the JSON. Their code lives in the "
            "database report_script field, where this guard cannot read it and cannot "
            "decide them either way",
        )

    def test_every_scoped_ref_a_report_names_has_a_readable_permissions_module(self):
        unreadable = sorted(
            {
                report.ref
                for report in self.reports.values()
                if report.ref in self.scoped and not permissions_exports(self.scoped[report.ref])
            }
        )
        self.assertEqual(
            unreadable, [], "a scoped ref's permissions module could not be read off disk"
        )


class TestEveryScopedRefReportAppliesItsScope(unittest.TestCase):
    """The A-217 invariant, against the shipped tree."""

    def setUp(self):
        self.scoped = scope_owning_modules()
        self.reports = shipped_script_reports()
        self.doctypes = shipped_doctypes()

    def test_no_unexempted_report_reads_a_scoped_doctype_unscoped(self):
        found = unscoped_reports(self.reports, self.scoped)
        expected = {name: ref for name, (ref, _why) in SCOPE_EXEMPT_REPORTS.items()}
        added = sorted(set(found) - set(expected))
        closed = sorted(set(expected) - set(found))
        self.assertEqual(
            (found, added, closed),
            (expected, [], []),
            "Script Report row-scoping changed.\n"
            + "".join(f"  NEW      {name} (ref {found[name]})\n" for name in added)
            + "".join(f"  CLOSED   {name}\n" for name in closed)
            + "A NEW entry means that report queries a row-scoped DocType with no scope "
            "resolved on the path execute takes, so every role that can open it reads "
            "every scope's rows — Script Report SQL never sees permission_query_conditions. "
            "Call the scope helper of the permissions module hooks.py names for the ref "
            "before querying, or add an exemption with a written reason. A CLOSED entry "
            "means one was fixed and this baseline must shrink to match.",
        )

    def test_every_exemption_carries_a_written_reason(self):
        for name, (ref, why) in SCOPE_EXEMPT_REPORTS.items():
            with self.subTest(report=name):
                self.assertTrue(ref, f"{name} is exempted with no ref_doctype named")
                self.assertTrue(why and why.strip(), f"{name} is exempted with no reason")

    def test_no_exemption_names_a_report_that_stopped_shipping(self):
        phantom = sorted(set(SCOPE_EXEMPT_REPORTS) - set(self.reports))
        self.assertEqual(
            phantom, [], "the exemption set names Script Report(s) this app no longer ships"
        )

    def test_no_exemption_names_a_ref_that_stopped_being_scoped(self):
        """An exemption from a boundary that no longer exists is dead weight, not a pardon."""
        stale = sorted(
            name
            for name, (ref, _why) in SCOPE_EXEMPT_REPORTS.items()
            if ref not in self.scoped or self.reports.get(name, ScriptReport(None, (), None)).ref != ref
        )
        self.assertEqual(
            stale,
            [],
            "exemption entr(ies) name a ref that is no longer row-scoped, or no longer the "
            "report's ref_doctype — prune them instead of leaving a pardon nobody reviewed",
        )

    def test_every_exemption_audience_is_unscoped_for_its_ref(self):
        """The machine-checkable half of every exemption, re-run on each build.

        A written reason is a claim about today. This is the part that keeps being true:
        an exemption survives only while every role that can OPEN the report is exempt
        from the ref's row scope anyway, so no boundary is crossed. Grant the report to a
        scoped role and the exemption fails here rather than ageing into a hole.
        """
        for name, (ref, _why) in SCOPE_EXEMPT_REPORTS.items():
            with self.subTest(report=name):
                report = self.reports[name]
                exempt = scope_exempt_roles(self.scoped[ref])
                scoped_readers = sorted(report_audience(report, self.doctypes) - exempt)
                self.assertEqual(
                    scoped_readers,
                    [],
                    f"{name} is exempted from re-applying {ref}'s row scope, but "
                    f"{scoped_readers} can open it and {ref} IS scoped for them. The "
                    "exemption's premise no longer holds: either the report must apply the "
                    "scope, or the role must come off its roles table.",
                )


class TestTheDetectorCanFail(unittest.TestCase):
    """Every clause driven with synthetic sources, so green is never vacuous.

    Each plant is paired with a control that must stay clean — the difference between
    "the detector fires" and "the detector fires at everything".
    """

    REF = "_A217 Source"
    REPORT = "_A217 Planted Report"
    MODULE = "apex.salis.permissions"
    HELPER = "report_project_scope"

    CLEAN = (
        "from apex.salis import permissions\n"
        "def execute(filters=None):\n"
        "    restrict, allowed = permissions.report_project_scope('u')\n"
        "    return [], []\n"
    )
    PLANTED = (
        "import frappe\n"
        "def execute(filters=None):\n"
        "    rows = frappe.get_all('Dispatch Trip', fields=['name', 'driver'])\n"
        "    return [], rows\n"
    )

    def setUp(self):
        self.exported = permissions_exports(self.MODULE)

    def _found(self, source_text, ref=None, module=None):
        """Drive unscoped_reports over one synthetic report with a real source file."""
        handle = tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8")
        handle.write(source_text)
        handle.close()
        self.addCleanup(os.unlink, handle.name)
        reports = {self.REPORT: ScriptReport(ref or self.REF, ("_A217 Role",), handle.name)}
        return unscoped_reports(reports, {ref or self.REF: module or self.MODULE})

    def test_a_report_that_calls_the_helper_stays_clean(self):
        """The control. Without it a detector that flagged everything would look right."""
        self.assertEqual(self._found(self.CLEAN), {})

    def test_a_report_that_never_calls_the_helper_is_flagged(self):
        self.assertEqual(self._found(self.PLANTED), {self.REPORT: self.REF})

    def test_a_scope_call_execute_never_reaches_is_flagged(self):
        """A helper nothing runs is not a filter, however correct it reads."""
        parked = (
            "from apex.salis import permissions\n"
            "def _unused():\n"
            "    return permissions.report_project_scope('u')\n"
            "def execute(filters=None):\n"
            "    return [], []\n"
        )
        self.assertEqual(self._found(parked), {self.REPORT: self.REF})

    def test_a_scope_call_in_a_helper_execute_does_reach_stays_clean(self):
        """Control for the clause above: 7 shipped reports scope in a fetch helper."""
        reached = (
            "from apex.salis import permissions\n"
            "def _rows():\n"
            "    return permissions.report_project_scope('u')\n"
            "def execute(filters=None):\n"
            "    return [], _rows()\n"
        )
        self.assertEqual(self._found(reached), {})

    def test_the_by_name_import_spelling_counts(self):
        """Two habitat reports import the helper directly rather than via an alias."""
        by_name = (
            "from apex.habitat.permissions import report_maintenance_request_scope\n"
            "def execute(filters=None):\n"
            "    restrict, user = report_maintenance_request_scope()\n"
            "    return [], []\n"
        )
        found = self._found(by_name, ref="_A217 Habitat Ref", module="apex.habitat.permissions")
        self.assertEqual(found, {})

    def test_the_primitive_pair_spelling_counts(self):
        """Five habitat reports filter with _building_is_unscoped / _allowed_buildings."""
        primitives = (
            "from apex.habitat import permissions\n"
            "def execute(filters=None):\n"
            "    if not permissions._building_is_unscoped('u'):\n"
            "        return [], []\n"
            "    return [], []\n"
        )
        found = self._found(primitives, ref="_A217 Habitat Ref", module="apex.habitat.permissions")
        self.assertEqual(found, {})

    def test_another_modules_helper_does_not_scope_this_ref(self):
        """A Building is not scoped by asking salis which projects a user may see."""
        wrong = (
            "from apex.salis import permissions\n"
            "def execute(filters=None):\n"
            "    restrict, allowed = permissions.report_project_scope('u')\n"
            "    return [], []\n"
        )
        found = self._found(wrong, ref="_A217 Habitat Ref", module="apex.habitat.permissions")
        self.assertEqual(found, {"_A217 Planted Report": "_A217 Habitat Ref"})

    def test_calling_a_name_the_permissions_module_does_not_define_is_flagged(self):
        """The vocabulary is the module's own exports, not any attribute access."""
        invented = (
            "from apex.salis import permissions\n"
            "def execute(filters=None):\n"
            "    allowed = permissions.definitely_not_a_real_helper('u')\n"
            "    return [], []\n"
        )
        self.assertEqual(self._found(invented), {self.REPORT: self.REF})

    def test_a_report_over_an_unscoped_ref_is_never_flagged(self):
        """Only DocTypes hooks.py actually scopes carry the obligation."""
        reports = {self.REPORT: ScriptReport("_A217 Unscoped Ref", (), __file__)}
        self.assertEqual(unscoped_reports(reports, {self.REF: self.MODULE}), {})

    def test_removing_the_module_check_lets_the_wrong_helper_through(self):
        """The mutant: accept any call, and a salis helper starts 'scoping' a Building."""
        tree = ast.parse(
            "from apex.salis import permissions\n"
            "def execute(filters=None):\n"
            "    return permissions.report_project_scope('u')\n"
        )
        blind = any(isinstance(node, ast.Call) for node in ast.walk(tree))
        self.assertTrue(blind, "the mutant would not fire, so this clause is unproven")
        self.assertFalse(
            applies_scope(
                ast.unparse(tree), "apex.habitat.permissions",
                permissions_exports("apex.habitat.permissions"),
            ),
            "the real detector accepts a foreign module's helper — the clause is dead",
        )


class TestTheEnumerationIsLive(unittest.TestCase):
    """The proof the scoped set is READ, not written down: scope one more DocType.

    ``Housing Checkout`` ships today with no permission_query_conditions entry, and
    ``Checkout Pending Clearance`` is its Script Report, which resolves no scope. Scope
    the DocType in a mirrored hooks file — no shipped file is touched — and the report
    must appear as an offender with nothing else in this module changed. A hardcoded
    DocType list could not produce that.
    """

    NEW_REF = "Housing Checkout"
    NEW_REPORT = "Checkout Pending Clearance"
    HANDLER = "apex.habitat.permissions.accommodation_assignment_query"

    def setUp(self):
        self.reports = shipped_script_reports()
        self.real = scope_owning_modules()

    def test_the_doctype_is_genuinely_unscoped_today(self):
        """The premise. If it were already scoped the proof below would prove nothing."""
        self.assertNotIn(self.NEW_REF, self.real)
        self.assertEqual(self.reports[self.NEW_REPORT].ref, self.NEW_REF)
        self.assertNotIn(self.NEW_REPORT, unscoped_reports(self.reports, self.real))

    def test_scoping_it_in_a_mirrored_hooks_flags_its_report(self):
        mirror = _mirror_hooks_with(self.NEW_REF, self.HANDLER)
        self.addCleanup(os.unlink, mirror)
        mirrored = scope_owning_modules(mirror)
        self.assertEqual(
            set(mirrored) - set(self.real),
            {self.NEW_REF},
            "the mirror changed more than the one entry it was supposed to add",
        )
        found = unscoped_reports(self.reports, mirrored)
        self.assertIn(
            self.NEW_REPORT,
            found,
            "a newly scoped DocType did not put its unfiltered report in the offender set, "
            "so the enumeration is not live",
        )
        self.assertEqual(
            set(found) - set(unscoped_reports(self.reports, self.real)),
            {self.NEW_REPORT},
            "scoping one DocType moved more than that DocType's report",
        )


if __name__ == "__main__":
    unittest.main()
