# Copyright (c) 2026, AFMCO and contributors
"""Subject: a Script Report over a row-scoped DocType that forgets to re-apply the scope.

``permission_query_conditions`` is a LIST-view mechanism: ``frappe/model/db_query.py``
composes it into the WHERE clause, so every desk list, link search and
``frappe.get_list`` inherit the row boundary free. A Script Report inherits nothing:
``frappe/desk/query_report.py`` checks ``frappe.has_permission(ref_doctype, "report")``
ONCE at :47, then runs ``execute()``, whose queries are ``frappe.get_all`` (forces
``ignore_permissions=True``) or raw SQL, neither touching the fragment. So the scope
survives only because the report re-applies it in Python -- this guard's sole
enforcement of that convention.

THE RULE: a report applies the scope when it CALLS a function the permissions module
``hooks.py`` names for its ``ref_doctype``, from ``execute`` or a function ``execute``
reaches in the same file -- deliberately not a name allowlist. 5 spellings are in use
app-wide: ``report_building_scope`` (12 habitat reports), ``report_project_scope`` (12
salis), ``report_company_scope`` (6 logistay), ``_building_is_unscoped`` paired with
``_allowed_buildings`` (5 habitat reports), and ``report_maintenance_request_scope``,
imported by name (2 habitat reports, the only owner/assignee scope in the set). All five
live in an ``apex/*/permissions.py``, so a SIXTH helper added tomorrow satisfies the
rule too. Two clauses make it hard to satisfy accidentally: the call must resolve FOR
THAT REF (a habitat report calling a salis helper does not scope a Building), and it
must sit in ``execute`` or a function ``execute`` reaches. All 32 clean reports satisfy
this: 26 directly in ``execute``, 6 in a fetch helper.

WHAT THIS STATIC CHECK CANNOT SEE: it proves the scope is RESOLVED, not USED --
``apex/tests/test_report_scope.py`` covers use for the 8 reports it drives, asserting
the filter reaches ``frappe.get_all``. A Script Report whose code lives in the database
``report_script`` field has no source to read; none ship today, and
``test_every_script_report_ships_a_python_module`` keeps it that way. The invariant is
keyed on ``ref_doctype``: a report whose ref is UNSCOPED but joins a scoped DocType sits
outside it -- ``Transport Fulfilment SLA`` (ref ``Trip Fulfilment Ledger``, joins
Transport Request) ships this way. ``Checkout Pending Clearance`` (ref ``Housing
Checkout``) does not: ``Housing Checkout`` is row-scoped in ``hooks.py`` and the report
resolves the scope. Not made a ratchet -- scanning for DocType names as string literals
returns 10 reports, 8 of them Link column ``options`` rather than queries, 20 percent
precision -- so it is recorded here as a finding instead.

Run standalone:  python3 -m unittest apex.salis.report.test_report_row_scope -v
"""

# SIZE: the subject is the 19 report PACKAGES under apex/salis/report/ (2,153 lines of
# .py + .json), not the 1-line __init__.py beside this file -- a per-directory count
# reads 443x and means nothing. Against the population actually swept, this file plus
# its sibling test_workspace_report_runnable.py come to 0.33x together, inside the 2x
# rule.
import ast
import glob
import json
import os
import tempfile
import unittest
from collections import namedtuple
from pathlib import Path

import apex
from apex.tests.shipped_doctypes import shipped_doctypes

_APP = str(Path(apex.__file__).resolve().parent)
_HOOKS = os.path.join(_APP, "hooks.py")
_REPORT_GLOB = os.path.join(_APP, "*", "report", "*", "*.json")

_FUNC = (ast.FunctionDef, ast.AsyncFunctionDef)
_ENTRYPOINT = "execute"

# Administrator short-circuits every permission check (frappe/permissions.py:107), so it
# is never the role a scope boundary is written for.
_ALWAYS_PERMITTED = frozenset({"Administrator"})

ScriptReport = namedtuple("ScriptReport", "ref roles source")

# Exact equality, like the sibling report baselines: a new offender fails the build, a
# repaired one must be pruned, so the set only shrinks. Each entry needs a written reason
# (test_every_exemption_carries_a_written_reason) and an audience still unscoped for its
# ref (test_every_exemption_audience_is_unscoped_for_its_ref), so freezing an entry is
# never a permanent pardon.

# apex/patches/v2_3/retire_replaced_reports.py retires "Movement KPI Summary": the package
# apex/salis/report/movement_kpi_summary/ no longer ships, so a baseline entry naming it
# fails test_no_exemption_names_a_report_that_stopped_shipping and
# test_every_exemption_audience_is_unscoped_for_its_ref (KeyError). Left empty, not
# deleted, so the next genuine exemption still has somewhere to land.
SCOPE_EXEMPT_REPORTS = {}


def _text(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def _string_constants(tree):
    """Top-level ``NAME = "…"`` assignments in the parsed module.

    ``permission_query_conditions`` names a shared constant (``_SALIS_SCOPE_QUERY``)
    for most of its entries rather than repeating one dotted path per DocType, so the
    dict values are ``ast.Name`` nodes and ``ast.literal_eval`` cannot read them.
    """
    constants = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not (isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                constants[target.id] = node.value.value
    return constants


def scope_owning_modules(hooks_path=_HOOKS):
    """``{DocType: dotted permissions module}`` from hooks.permission_query_conditions.

    The single enumeration point: row-scoped DocTypes are read live from here, never from
    a list hardcoded elsewhere, so a DocType scoped tomorrow is covered the day its hook
    entry lands. The hook VALUE also names the module OWNING the scope (e.g.
    ``apex.habitat.permissions.accommodation_assignment_query``), so a caller knows which
    vocabulary a report over that DocType must speak. Parsed rather than imported so the
    guard runs with no site and no frappe, and so a test can drive it against a mirrored
    hooks file to prove the enumeration is live rather than hardcoded. A handler written
    as a literal and one written as a module constant both resolve.
    """
    tree = ast.parse(_text(hooks_path))
    constants = _string_constants(tree)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        named = [t.id for t in node.targets if isinstance(t, ast.Name)]
        if "permission_query_conditions" not in named:
            continue
        if not isinstance(node.value, ast.Dict):
            return {}
        handlers = {}
        for key, value in zip(node.value.keys, node.value.values):
            if not (isinstance(key, ast.Constant) and isinstance(key.value, str)):
                continue
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                handler = value.value
            elif isinstance(value, ast.Name):
                handler = constants.get(value.id)
            else:
                handler = None
            if handler:
                handlers[key.value] = handler.rsplit(".", 1)[0]
        return handlers
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
        # Both skips are asserted empty by test_every_script_report_ships_a_python_module,
        # so neither can hide an offender behind a shrug.
        if not exported or report.source is None:
            continue
        if not applies_scope(_text(report.source), dotted, exported):
            found[name] = report.ref
    return found


def skipped_reports(reports, scoped):
    """``{report: reason}`` for every scoped-ref report ``unscoped_reports`` cannot scan.

    Mirrors that function's two ``continue`` guards. A report dropped here is invisible to
    this sweep -- neither counted clean nor flagged -- so this set has to be asserted
    empty rather than trusted from a comment.
    """
    found = {}
    for name, report in sorted(reports.items()):
        dotted = scoped.get(report.ref)
        if dotted is None:
            continue
        exported = permissions_exports(dotted)
        if not exported:
            found[name] = f"{dotted} exports no scope-check function to call"
        elif report.source is None:
            found[name] = "ships no readable Python module (report_script only, or no .py on disk)"
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


# Concrete hazard this guards: Resident Supervisor holds `report` on Housing Assignment
# and is not in habitat/permissions.py HOUSING_UNSCOPED_ROLES, so it is building-scoped
# there. All three shipped Housing Assignment reports call report_building_scope before
# querying; a report that omits the call would hand the role every building's resident
# records unnoticed.
class TestEveryScopedRefReportAppliesItsScope(unittest.TestCase):
    """The row-scope invariant, against the shipped tree."""

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

    def test_every_script_report_ships_a_python_module(self):
        """The silent half of this sweep: nothing may be dropped from it unseen.

        ``unscoped_reports`` skips a report whose permissions module exports nothing, or
        whose own ``.py`` source is missing, instead of flagging it -- so an offender in
        either shape would read as clean by never being counted. This asserts the drop set
        stays empty, making good on the claim the loop's own comment already made.
        """
        found = skipped_reports(self.reports, self.scoped)
        self.assertEqual(
            found,
            {},
            "Script Report(s) over a scoped ref cannot be swept for row-scope compliance:\n"
            + "".join(f"  {name}: {reason}\n" for name, reason in sorted(found.items())),
        )

    def test_scope_owning_modules_reads_the_mirrored_hooks_file_live(self):
        """The enumeration is driven by the hooks file handed in, not hardcoded.

        A mirrored hooks.py carrying one extra permission_query_conditions entry must
        produce that one extra DocType alongside every DocType the shipped file already
        scopes -- proving scope_owning_modules() re-parses hooks_path rather than reading
        some fixed snapshot of today's tree."""
        mirror = _mirror_hooks_with(
            "Apex Mirrored Probe DocType",
            "apex.habitat.permissions.accommodation_assignment_query",
        )
        self.addCleanup(os.remove, mirror)
        mirrored = scope_owning_modules(hooks_path=mirror)
        self.assertEqual(
            mirrored.get("Apex Mirrored Probe DocType"), "apex.habitat.permissions"
        )
        self.assertLessEqual(set(self.scoped), set(mirrored))


if __name__ == "__main__":
    unittest.main()
