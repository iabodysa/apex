# Copyright (c) 2026, AFMCO and contributors
"""A-189 — a workspace Report link renders for a role whose ref_doctype forbids running it.

SUBJECT: the 19 report PACKAGES under apex/salis/report/ (2,153 lines) crossed with the
Salis and Fleet workspace records, not the 1-line ``__init__.py`` beside this file. The
258x a per-directory count reports is a grouping artifact; with test_report_row_scope.py,
which sweeps the same population, this comes to 0.33x — inside the 2x rule, no exception
claimed.

``Workspace.is_item_allowed`` clears a Report link on the report's ``roles`` child table
ALONE (``frappe/desk/desktop.py:155-158`` -> ``boot.get_allowed_reports`` ->
``get_user_pages_or_reports``, boot.py:249-268, which joins only ``Has Role``). It never
looks at ``ref_doctype``. Opening the report then goes through
``frappe/desk/query_report.py:47``, which throws PermissionError unless
``frappe.has_permission(ref_doctype, "report")``. So the link renders live and dies on
click, with no clue on the workspace that it would.

Three shapes make ``has_permission(ref, "report")`` False for a role:

1. ``ref_doctype`` is a child table — ``frappe/permissions.py:120`` routes to
   ``has_child_permission``, which returns False at :785 when no ``parent_doctype`` is
   supplied, and query_report supplies none. This is the A-178b instance (Vehicle
   Compliance Register); the whole-app clause for it lives in
   ``test_report_role_coverage.TestReportRefDoctypeIsRunnable``, which covers reports
   with no workspace link too, so neither guard subsumes the other.
2. The role holds no permlevel-0 DocPerm on the ref at all.
3. The role holds one, but the row does not set ``report``.

Shape 3 is the common one and is NOT cosmetic. ``DocPerm.report`` has ``default: 1`` in
``frappe/core/doctype/docperm/docperm.json``, so it is easy to assume an omitted flag
becomes 1 on import. It does not: ``frappe/modules/import_file.py:212`` puts the
framework into import mode, which makes ``Document._set_defaults`` return at
document.py:834 before any field default is applied, and ``BaseDocument.get_valid_dict``
then coerces the unset Check field to 0 at base_document.py:394. The row lands with
``report=0`` and the column default never fires. Verified read-only against the live
bench DB: ``Accommodation Ledger`` / ``System Manager`` ships ``{"read": 1, "role":
"System Manager"}`` and stores ``report=0``.

``if_owner`` is a fourth way to lose the right even with ``report: 1`` on the row:
``get_role_permissions`` (permissions.py:297-307) zeroes every ptype outside
``("select", "read")`` when the only rows granting it are if_owner rows, so an
if_owner-only ``report`` grant still denies. ``permlevel`` above 0 never counts at all
(permissions.py:284).

The audience of a link is ``workspace roles INTERSECT report roles`` — a report with an
empty roles table is open to everyone, so it inherits the workspace's grant list
(boot.py:275-285). Roles are evaluated one at a time, modelling a persona user who holds
exactly that role; that is the population a workspace grant is written for.

Scope: every module's workspace tree, ``links`` and ``shortcuts`` alike — ``get_shortcuts``
(desktop.py:299) runs the same ``is_item_allowed`` check. No Report shortcut ships today;
covering it costs nothing and stops the next one arriving unguarded.

A-200 drained the baseline to empty. All 34 (ref_doctype, role) pairs behind the original
27 links were resolved as access decisions, not flag flips: 30 rows that already held a
permlevel-0 read gained an explicit ``"report": 1``; ``Internal Auditor`` gained the
app's standard read/report/export oversight row on ``Audit Remediation Plan`` and
``Operational Depreciation Snapshot``; and two roles were dropped from six reports whose
source DocPerms never admitted them (``Accommodation Manager`` off the four Accommodation
Ledger reports, ``Resident Supervisor`` off the two Accommodation Stock Ledger reports).
Every grant on a row-scoped source was checked against that source's
``permission_query_conditions`` scope: each report self-scopes before it queries, so no
role gained rows outside the estate or project it is held inside.

This module sits beside ``test_report_role_coverage.py`` for the reason that file records:
the invariant spans the workspace, report and doctype trees of every module, so it owns no
single home, and the central ``apex/tests/`` directory is shrink-only
(``test_colocation_ratchet.py``).

Run standalone:  python3 -m unittest apex.salis.report.test_workspace_report_runnable -v
"""

import glob
import json
import os
import unittest
from pathlib import Path

import apex
from apex.tests.shipped_doctypes import shipped_doctypes

_APP = str(Path(apex.__file__).resolve().parent)
_WORKSPACE_GLOB = os.path.join(_APP, "*", "workspace", "*", "*.json")
_REPORT_GLOB = os.path.join(_APP, "*", "report", "*", "*.json")

# Administrator short-circuits every permission check (permissions.py:107, and
# is_item_allowed returns True for it before any lookup), so it is never the bug.
_ALWAYS_PERMITTED = frozenset({"Administrator"})

# A-200 emptied this. Every workspace Report link is now runnable by every role it is
# shown to, so the baseline is exact-equality against {} — one new offender fails the build.
# An entry added here needs a written reason (test_every_frozen_pair_carries_a_reason).
KNOWN_UNRUNNABLE_REPORT_LINKS = {}


def _load(pattern, doctype):
    """name -> shipped JSON, for every record of one type under the app tree."""
    out = {}
    for path in sorted(glob.glob(pattern)):
        with open(path, encoding="utf-8") as fh:
            try:
                data = json.load(fh)
            except json.JSONDecodeError:
                continue
        if isinstance(data, dict) and data.get("doctype") == doctype and data.get("name"):
            out[data["name"]] = data
    return out


def _shipped_workspaces():
    return _load(_WORKSPACE_GLOB, "Workspace")


def _shipped_reports():
    return _load(_REPORT_GLOB, "Report")


def _roles_named(record):
    """Roles in a record's `roles` child table; empty means "open to everyone"."""
    return {row["role"] for row in (record.get("roles") or []) if row.get("role")}


def _report_links(workspace):
    """Report names this workspace renders, from both link cards and shortcuts."""
    names = [
        item.get("link_to")
        for item in (workspace.get("links") or [])
        if item.get("type") == "Link" and item.get("link_type") == "Report"
    ]
    names += [
        item.get("link_to")
        for item in (workspace.get("shortcuts") or [])
        if item.get("type") == "Report"
    ]
    return [name for name in names if name]


def _roles_that_can_run(ref_doctype, doctypes):
    """Roles for which has_permission(ref_doctype, "report") is True, per frappe's rules.

    Mirrors get_role_permissions: permlevel-0 rows only (permissions.py:284), and an
    if_owner row cannot carry `report` because permissions.py:307 rewrites every ptype
    outside ("select", "read") back to 0 when no plain row grants it. A child table can
    never grant it at all — query_report passes no parent doc, so has_child_permission
    denies (permissions.py:785).

    Returns None when the ref is not shipped by this app, so the caller can tell "no role
    may run this" apart from "this guard cannot see the DocPerms".
    """
    data = doctypes.get(ref_doctype)
    if data is None:
        return None
    if data.get("istable"):
        return set()
    return {
        row["role"]
        for row in (data.get("permissions") or [])
        if row.get("role")
        and row.get("report")
        and not row.get("if_owner")
        and not int(row.get("permlevel") or 0)
    }


def _unrunnable_links(workspaces, reports, doctypes):
    """{"workspace :: report": {roles that see the link but cannot run it}}.

    Pure over its inputs so the planted-violation proofs below can drive it with synthetic
    records instead of asserting only against whatever happens to be on disk today.
    """
    found = {}
    for workspace_name, workspace in workspaces.items():
        granted = _roles_named(workspace)
        for report_name in _report_links(workspace):
            report = reports.get(report_name)
            if report is None:
                continue
            audience = _roles_named(report)
            # An empty roles table on the report means every workspace role sees it.
            audience = (audience & granted) if audience else set(granted)
            allowed = _roles_that_can_run(report.get("ref_doctype"), doctypes)
            if allowed is None:
                continue
            denied = audience - allowed - _ALWAYS_PERMITTED
            if denied:
                found[f"{workspace_name} :: {report_name}"] = denied
    return found


def _sorted_names(mapping):
    return {key: sorted(value) for key, value in mapping.items()}


def _flatten(mapping):
    """{"workspace :: report": [roles]} -> {"workspace :: report -> role"} for a named diff."""
    return {f"{link} -> {role}" for link, roles in mapping.items() for role in roles}


class TestEveryVisibleReportLinkIsRunnable(unittest.TestCase):
    """The A-189 invariant: seeing a Report link must imply being able to run it."""

    def setUp(self):
        self.workspaces = _shipped_workspaces()
        self.reports = _shipped_reports()
        self.doctypes = shipped_doctypes()

    def test_the_scan_reaches_the_shipped_tree(self):
        """The population, asserted, because every clause below passes over an empty one.

        This guard spent the period after the suite moved out of the app reading a
        directory that holds no JSON: zero workspaces, zero reports, zero DocTypes, and
        a green tick over all three.
        """
        self.assertGreater(len(self.workspaces), 0, "no shipped workspace was read")
        self.assertGreater(len(self.reports), 0, "no shipped report was read")
        self.assertGreater(len(self.doctypes), 0, "no shipped DocType was read")
        linked = [name for ws in self.workspaces.values() for name in _report_links(ws)]
        self.assertGreater(len(linked), 0, "no workspace Report link was found to grade")

    def test_no_new_unrunnable_report_link(self):
        found = _sorted_names(_unrunnable_links(self.workspaces, self.reports, self.doctypes))
        expected = _sorted_names(KNOWN_UNRUNNABLE_REPORT_LINKS)
        # Report the delta by name. A raw dict comparison of 27 entries truncates to
        # "[1884 chars]", which tells the reader nothing about WHICH pair moved.
        added = sorted(_flatten(found) - _flatten(expected))
        closed = sorted(_flatten(expected) - _flatten(found))
        self.assertEqual(
            (added, closed),
            ([], []),
            "workspace Report link runnability changed.\n"
            + "".join(f"  NEW      {pair}\n" for pair in added)
            + "".join(f"  CLOSED   {pair}\n" for pair in closed)
            + "A NEW pair means that role sees the link on its workspace and gets a "
            "PermissionError from frappe/desk/query_report.py:47 on click — grant `report` "
            "on the ref_doctype row it already holds, drop the role from the report's roles "
            "table, or point ref_doctype at the DocType whose DocPerms actually govern the "
            "rows. A CLOSED pair means an access bug was fixed and this baseline must "
            "shrink to match.",
        )

    def test_every_frozen_pair_carries_a_reason(self):
        for link, roles in KNOWN_UNRUNNABLE_REPORT_LINKS.items():
            for role, reason in roles.items():
                with self.subTest(link=link, role=role):
                    self.assertTrue(
                        reason and reason.strip(),
                        f"frozen pair {link} / {role} has no documented reason",
                    )

    def test_the_baseline_holds_no_phantom_link(self):
        """A pair frozen for a link that no longer exists would widen the ratchet."""
        live = {
            f"{workspace_name} :: {report_name}"
            for workspace_name, workspace in self.workspaces.items()
            for report_name in _report_links(workspace)
        }
        phantom = sorted(set(KNOWN_UNRUNNABLE_REPORT_LINKS) - live)
        self.assertEqual(
            phantom, [], "baseline entr(ies) name a workspace Report link that no longer ships"
        )


if __name__ == "__main__":
    unittest.main()
