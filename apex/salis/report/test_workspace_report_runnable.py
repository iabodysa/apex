# Copyright (c) 2026, AFMCO and contributors
"""A-189 — a workspace Report link renders for a role whose ref_doctype forbids running it.

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
becomes 1 on import. It does not: ``frappe/modules/import_file.py:212`` sets
``frappe.flags.in_import``, which makes ``Document._set_defaults`` return at
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

from apex.tests.shipped_doctypes import shipped_doctypes

_APP = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
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


class TestTheScanSeesTheWholeApp(unittest.TestCase):
    """A guard that silently scanned nothing would pass forever."""

    def setUp(self):
        self.workspaces = _shipped_workspaces()
        self.reports = _shipped_reports()
        self.doctypes = shipped_doctypes()

    def test_the_globs_find_records(self):
        self.assertTrue(self.workspaces, "no workspace JSON found — the glob broke")
        self.assertTrue(self.reports, "no report JSON found — the glob broke")
        self.assertTrue(self.doctypes, "no DocType JSON found — the glob broke")

    def test_every_module_workspace_tree_is_scanned(self):
        modules = {
            os.path.relpath(path, _APP).split(os.sep)[0]
            for path in glob.glob(_WORKSPACE_GLOB)
        }
        self.assertEqual(
            modules,
            {"habitat", "salis"},
            "the workspace glob no longer covers every module that ships a workspace",
        )

    def test_report_links_are_actually_found(self):
        total = sum(len(_report_links(w)) for w in self.workspaces.values())
        self.assertGreaterEqual(
            total, 40, f"only {total} workspace Report links found — the link parser broke"
        )

    def test_every_linked_report_resolves_to_shipped_json(self):
        """A link to a report this app does not ship would be skipped, not checked."""
        missing = sorted(
            {
                name
                for workspace in self.workspaces.values()
                for name in _report_links(workspace)
                if name not in self.reports
            }
        )
        self.assertEqual(
            missing, [], "workspace links name Report(s) with no shipped JSON to check"
        )

    def test_every_linked_report_ref_is_shipped_by_this_app(self):
        """Only refs this app ships have DocPerms the guard can read off disk."""
        unseen = sorted(
            {
                self.reports[name].get("ref_doctype")
                for workspace in self.workspaces.values()
                for name in _report_links(workspace)
                if name in self.reports
                and self.reports[name].get("ref_doctype") not in self.doctypes
            }
        )
        self.assertEqual(
            unseen,
            [],
            "a linked report points at a ref_doctype from another app, so this guard "
            "cannot see its DocPerms and silently skips the link",
        )


class TestEveryVisibleReportLinkIsRunnable(unittest.TestCase):
    """The A-189 invariant: seeing a Report link must imply being able to run it."""

    def setUp(self):
        self.workspaces = _shipped_workspaces()
        self.reports = _shipped_reports()
        self.doctypes = shipped_doctypes()

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


class TestTheDetectorCanFail(unittest.TestCase):
    """Every clause driven with synthetic records, so green is never vacuous.

    Each planted case fixes one variable against a control that must stay clean, which is
    what separates "the detector fires" from "the detector fires at everything".
    """

    REF = "_A189 Source"
    REPORT = "_A189 Planted Report"
    WORKSPACE = "_A189 Planted Workspace"
    ROLE = "_A189 Role"

    def _fixture(self, permission_row, *, istable=0, report_roles=None, workspace_roles=None):
        doctypes = {self.REF: {"istable": istable, "permissions": [permission_row]}}
        reports = {
            self.REPORT: {
                "ref_doctype": self.REF,
                "roles": [{"role": r} for r in (report_roles or [self.ROLE])],
            }
        }
        workspaces = {
            self.WORKSPACE: {
                "roles": [{"role": r} for r in (workspace_roles or [self.ROLE])],
                "links": [
                    {"type": "Link", "link_type": "Report", "link_to": self.REPORT},
                ],
            }
        }
        return _unrunnable_links(workspaces, reports, doctypes)

    def _key(self):
        return f"{self.WORKSPACE} :: {self.REPORT}"

    def test_a_ref_that_grants_report_stays_clean(self):
        """The control. Without it a detector that flags everything would look correct."""
        found = self._fixture({"role": self.ROLE, "read": 1, "report": 1})
        self.assertEqual(found, {}, "the detector flagged a link whose ref DOES grant report")

    def test_a_ref_that_omits_the_report_flag_is_flagged(self):
        found = self._fixture({"role": self.ROLE, "read": 1})
        self.assertEqual(found, {self._key(): {self.ROLE}})

    def test_a_ref_that_names_another_role_entirely_is_flagged(self):
        found = self._fixture({"role": "_A189 Other Role", "read": 1, "report": 1})
        self.assertEqual(found, {self._key(): {self.ROLE}})

    def test_a_child_table_ref_is_flagged_even_with_report_granted(self):
        """The A-178b shape: an istable ref denies everyone, however generous the row."""
        found = self._fixture({"role": self.ROLE, "read": 1, "report": 1}, istable=1)
        self.assertEqual(found, {self._key(): {self.ROLE}})

    def test_an_if_owner_only_report_grant_is_flagged(self):
        """permissions.py:307 rewrites `report` back to 0 when only if_owner rows grant it."""
        found = self._fixture({"role": self.ROLE, "read": 1, "report": 1, "if_owner": 1})
        self.assertEqual(found, {self._key(): {self.ROLE}})

    def test_a_plain_row_beside_an_if_owner_row_stays_clean(self):
        """Control for the clause above: a non-if_owner grant survives an if_owner sibling."""
        doctypes = {
            self.REF: {
                "permissions": [
                    {"role": self.ROLE, "read": 1, "report": 1, "if_owner": 1},
                    {"role": self.ROLE, "read": 1, "report": 1},
                ]
            }
        }
        reports = {self.REPORT: {"ref_doctype": self.REF, "roles": [{"role": self.ROLE}]}}
        workspaces = {
            self.WORKSPACE: {
                "roles": [{"role": self.ROLE}],
                "links": [{"type": "Link", "link_type": "Report", "link_to": self.REPORT}],
            }
        }
        self.assertEqual(_unrunnable_links(workspaces, reports, doctypes), {})

    def test_a_report_grant_above_permlevel_zero_is_flagged(self):
        """permissions.py:284 discards any row whose permlevel is not 0."""
        found = self._fixture({"role": self.ROLE, "read": 1, "report": 1, "permlevel": 1})
        self.assertEqual(found, {self._key(): {self.ROLE}})

    def test_a_role_outside_the_workspace_grant_never_sees_the_link(self):
        """Only the intersection is at risk; a report role with no workspace grant is not."""
        found = self._fixture(
            {"role": self.ROLE, "read": 1, "report": 1},
            report_roles=[self.ROLE, "_A189 Unlinked Role"],
        )
        self.assertEqual(found, {})

    def test_an_empty_report_roles_table_inherits_the_whole_workspace(self):
        """boot.py:275-285 admits a role-less report to everyone, so the audience widens."""
        found = self._fixture({"role": self.ROLE, "read": 1, "report": 1}, report_roles=[])
        self.assertEqual(found, {})
        found = self._fixture({"role": "_A189 Other Role", "read": 1, "report": 1}, report_roles=[])
        self.assertEqual(found, {self._key(): {self.ROLE}})

    def test_a_report_shortcut_is_scanned_like_a_link(self):
        """desktop.py:299 runs the same is_item_allowed check for shortcuts."""
        doctypes = {self.REF: {"permissions": [{"role": self.ROLE, "read": 1}]}}
        reports = {self.REPORT: {"ref_doctype": self.REF, "roles": [{"role": self.ROLE}]}}
        workspaces = {
            self.WORKSPACE: {
                "roles": [{"role": self.ROLE}],
                "shortcuts": [{"type": "Report", "link_to": self.REPORT}],
            }
        }
        self.assertEqual(_unrunnable_links(workspaces, reports, doctypes), {self._key(): {self.ROLE}})


class TestTheShippedJsonMatchesTheRuntimeReading(unittest.TestCase):
    """Anchors the guard's two load-bearing readings of frappe against real shipped data.

    Both are the kind of assumption that quietly rots: if either stops holding, the
    baseline above is measuring the wrong thing and this class says so out loud.
    """

    def setUp(self):
        self.doctypes = shipped_doctypes()

    def test_shipped_docperm_rows_both_omit_and_set_the_report_flag(self):
        """`report` is written explicitly where wanted, so an omission is a real 0.

        DocPerm.report has default 1 in frappe's own JSON, so "the flag is just never
        written in this app" would be an innocent explanation for the baseline. It is not:
        the app writes it on some rows and not others, on the same DocType.
        """
        with_flag = without_flag = 0
        for data in self.doctypes.values():
            for row in data.get("permissions") or []:
                if int(row.get("permlevel") or 0):
                    continue
                if row.get("report"):
                    with_flag += 1
                else:
                    without_flag += 1
        self.assertGreater(with_flag, 0, "no shipped DocPerm sets `report` — reading is wrong")
        self.assertGreater(
            without_flag,
            0,
            "every shipped permlevel-0 DocPerm now sets `report`, so an omission can no "
            "longer be told apart from a DocType this app simply never writes the flag on. "
            "Re-anchor the sample below before trusting the scan again.",
        )
        # Sampled on a DocType A-200 touched, so a future re-flattening of these rows lands
        # here first. Internal Auditor is the app's read/report/export oversight shape;
        # Resident Supervisor is an operator row that deliberately carries no `report`.
        sample = self.doctypes.get("Custody Damage Assessment")
        self.assertIsNotNone(sample, "the sampled DocType is gone; re-anchor this assertion")
        flags = {
            row["role"]: bool(row.get("report"))
            for row in sample["permissions"]
            if not int(row.get("permlevel") or 0)
        }
        self.assertEqual(
            flags.get("Internal Auditor"),
            True,
            "Custody Damage Assessment no longer grants Internal Auditor `report`",
        )
        self.assertEqual(
            flags.get("Resident Supervisor"),
            False,
            "Custody Damage Assessment / Resident Supervisor now sets `report`; if that was "
            "an access decision, re-anchor this sample on another both-shapes DocType",
        )

    def test_no_linked_report_declares_a_child_table_ref(self):
        """The A-178b instance stays fixed where it is actually rendered.

        The whole-app clause is in test_report_role_coverage; this one asserts it for the
        subset that a workspace puts in front of a user, which is where it drew blood.
        """
        reports = _shipped_reports()
        offenders = sorted(
            {
                name
                for workspace in _shipped_workspaces().values()
                for name in _report_links(workspace)
                if name in reports
                and (self.doctypes.get(reports[name].get("ref_doctype")) or {}).get("istable")
            }
        )
        self.assertEqual(
            offenders,
            [],
            "a linked report declares a child table as ref_doctype, so query_report denies "
            "every non-Administrator — point it at the DocType that embeds it",
        )


class TestNoReportAudienceEscapesTheStaticScan(unittest.TestCase):
    """Keep the two DB-only audience paths shut, so a file-level scan stays sufficient.

    This guard reads JSON off disk, so a Report CREATED IN THE DATABASE is invisible to it,
    and so is a ``Custom Role`` row — which is the sharper hole of the two, because
    ``boot.get_user_pages_or_reports`` (boot.py:222-233) resolves a report's audience from
    Custom Role FIRST and then EXCLUDES that report from the roles-table query at :254. One
    Custom Role row silently replaces a report's whole roles table, and no shipped file
    changes. Three such rows exist on the live bench today, all from hrms over Salary Slip.

    Neither can be found by scanning files, so instead this class pins the boundary that
    makes scanning files enough: apex must ship reports ONLY as module JSON, and must never
    ship or seed a Custom Role. While that holds, every audience this app defines is on
    disk. A release-hygiene rule cannot do better from static text; the runtime half — a
    Report ``validate`` that refuses roles their ref_doctype cannot grant ``report`` — is
    the structural fix and belongs in hooks, not here.
    """

    def test_the_app_ships_no_custom_role_record(self):
        found = []
        for path in glob.glob(os.path.join(_APP, "**", "*.json"), recursive=True):
            with open(path, encoding="utf-8") as fh:
                try:
                    data = json.load(fh)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue
            if isinstance(data, dict) and data.get("doctype") == "Custom Role":
                found.append(os.path.relpath(path, _APP))
        self.assertEqual(
            found,
            [],
            "apex ships a Custom Role record. It overrides the report's roles table in "
            "boot.py:222-254, so this guard's audience calculation would be wrong for it.",
        )

    def test_no_report_or_custom_role_is_delivered_as_a_fixture(self):
        """A fixture-delivered Report lands in the DB with no module JSON to scan."""
        from apex import hooks

        delivered = sorted(
            {
                entry["dt"] if isinstance(entry, dict) else entry
                for entry in (getattr(hooks, "fixtures", None) or [])
            }
            & {"Report", "Custom Role", "Has Role"}
        )
        self.assertEqual(
            delivered,
            [],
            "hooks.fixtures delivers report-audience records straight to the database, "
            "where this file-level scan cannot see them",
        )

    def test_every_shipped_report_lives_in_a_module_report_tree(self):
        """The glob's premise: no report JSON hides outside `<module>/report/<name>/`."""
        stray = []
        for path in glob.glob(os.path.join(_APP, "**", "*.json"), recursive=True):
            with open(path, encoding="utf-8") as fh:
                try:
                    data = json.load(fh)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue
            if not isinstance(data, dict) or data.get("doctype") != "Report":
                continue
            parts = os.path.relpath(path, _APP).split(os.sep)
            if len(parts) != 4 or parts[1] != "report":
                stray.append(os.path.relpath(path, _APP))
        self.assertEqual(stray, [], "a Report JSON sits outside the scanned module trees")


if __name__ == "__main__":
    unittest.main()
