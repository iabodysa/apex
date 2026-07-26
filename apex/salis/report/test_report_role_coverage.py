# Copyright (c) 2026, AFMCO and contributors
"""A-171/A-172 — a DocPerm holder absent from a Report's ``roles`` sees an empty card.

``Government Relations Officer`` held read DocPerms on Salis Vehicle / Salis Driver /
Driver Clearance / Driver Suspension / Vehicle Incident, was granted the
``Compliance and Rentals`` workspace, and still landed on a Reports card with nothing on
it: ``frappe/boot.py`` ``get_user_pages_or_reports`` returns a Report only when a row of
its ``Has Role`` child table names one of the session user's roles
(``pages_with_standard_roles``, boot.py:249-257), and a report whose ``roles`` table is
non-empty never falls into the "no role = allowed" branch (boot.py:275-279). The DocPerm
is necessary and not sufficient.

The framework already states the intended relationship: ``Report.set_doctype_roles``
(frappe/core/doctype/report/report.py:107-112) seeds a report's roles from
``[d.role for d in meta.permissions if d.permlevel == 0]``. This guard asserts that
correspondence for every shipped report, allowing a report to hold MORE roles than its
source DocType (a curated audience) but never to silently drop one.

Child-table ``ref_doctype`` (Vehicle Compliance Register reads ``Salis Vehicle
Compliance``) resolves to the embedding parent, because a child table carries no DocPerms
of its own and its rows are governed by the parent's.

Scope: A-172 widened the glob from Salis alone to EVERY module's report tree — Habitat
and Logistay included. Logistay was already clean; Habitat contributed 13 reports whose
roles tables drop a reader, all frozen below with a reason and carried by their own card.
A-172 fixed only the two it was scoped to, the pair built for ``Safety Officer``.

The file stays under ``salis/report`` because it began as the Salis guard and the central
``apex/tests/`` directory is closed to new modules (test_colocation_ratchet.py); a
cross-module invariant has no single module to sit beside.

Run standalone:  python3 -m unittest apex.salis.report.test_report_role_coverage -v
"""

import glob
import json
import os
import unittest

from apex.tests.shipped_doctypes import shipped_doctypes
from apex.tests.training_charter import role_charters

_REPORT_DIR = os.path.dirname(os.path.abspath(__file__))
_APP = os.path.normpath(os.path.join(_REPORT_DIR, "..", ".."))
_REPORT_GLOB = os.path.join(_APP, "*", "report", "*", "*.json")
_DOCTYPE_GLOB = os.path.join(_APP, "*", "doctype", "*", "*.json")

GRO_ROLE = "Government Relations Officer"
SAFETY_ROLE = "Safety Officer"

# The word in the published Safety Officer charter that makes a report over Safety Task
# Execution in-charter. A lookup key into docs/training/README.md, not a copy of it.
SAFETY_CAPABILITY = "executions"

# System Manager reaches every report through the Report DocType itself, so its absence
# from a roles table is never the bug this guard hunts.
_ALWAYS_PERMITTED = {"System Manager", "Administrator"}

_FROZEN = (
    "Pre-existing when the A-171 guard landed. The role reads the source DocType but was "
    "never added to this report's roles table; A-171 scoped its audit to the Government "
    "Relations Officer persona only. Ratchet entry — review and remove, never grow."
)

_SELF_SERVICE = (
    "Holds an if_owner-only DocPerm (own records, no desk access). Granting it the report "
    "would put a whole-fleet register in front of a single driver — a deliberate exclusion."
)

_FROZEN_HABITAT = (
    "Pre-existing when A-172 widened this guard past Salis. The role holds a permlevel-0 "
    "read DocPerm on the source DocType but was never added to this report's roles table; "
    "A-172 fixed only the Safety Officer pair it was scoped to. Ratchet entry — review and "
    "remove, never grow."
)

_ALL_ROLE_IF_OWNER = (
    "Maintenance Request grants `All` an if_owner-only read row, so a resident sees only "
    "the request they raised. `All` is held by every session, so naming it in a report's "
    "roles table publishes the whole building's maintenance backlog to everyone — a "
    "deliberate exclusion, not an oversight."
)

KNOWN_REPORT_ROLE_GAPS = {
    # Frozen baseline of role -> reason, per report. The assertion is exact equality: a NEW
    # pair fails the build and a CLOSED pair fails until it is pruned from here.
    "Accommodation Stock Balance": {
        "Finance Manager": _FROZEN_HABITAT,
        "Internal Auditor": _FROZEN_HABITAT,
    },
    "Custody Damage Register": {"Resident Supervisor": _FROZEN_HABITAT},
    "Custody Outstanding by Worker": {
        "Finance Manager": _FROZEN_HABITAT,
        "Internal Auditor": _FROZEN_HABITAT,
    },
    "Daily Cleaning Compliance": {
        "Cleaning Supervisor": _FROZEN_HABITAT,
        "Internal Auditor": _FROZEN_HABITAT,
    },
    "Intercompany Movement Register": {"Resident Supervisor": _FROZEN_HABITAT},
    "Lease Expiry Watchlist": {"Internal Auditor": _FROZEN_HABITAT},
    "Maintenance Aging": {
        "All": _ALL_ROLE_IF_OWNER,
        "Maintenance Technician": _FROZEN_HABITAT,
        "Resident Request Coordinator": _FROZEN_HABITAT,
    },
    "Missed Cleaning Tasks": {
        "Cleaning Supervisor": _FROZEN_HABITAT,
        "Internal Auditor": _FROZEN_HABITAT,
    },
    "Occupancy Trend": {
        "Internal Auditor": _FROZEN_HABITAT,
        "Resident Supervisor": _FROZEN_HABITAT,
    },
    "Open Maintenance Requests": {
        "All": _ALL_ROLE_IF_OWNER,
        "Maintenance Technician": _FROZEN_HABITAT,
        "Resident Request Coordinator": _FROZEN_HABITAT,
    },
    "Operational Depreciation Aging": {"Resident Supervisor": _FROZEN_HABITAT},
    "Supplier Cost Recovery": {"Internal Auditor": _FROZEN_HABITAT},
    "Utility Variance": {"Internal Auditor": _FROZEN_HABITAT},
    "Cost Recovery Aging": {"Fleet Supervisor": _FROZEN},
    "Driver Attendance Summary": {
        "Driver": _SELF_SERVICE,
        "Internal Auditor": _FROZEN,
    },
    "Driver Clearance Register": {
        "Finance Manager": _FROZEN,
        "Fleet Supervisor": _FROZEN,
    },
    "Fleet Payment Register": {
        "Fleet Project Manager": _FROZEN,
        "Fleet Supervisor": _FROZEN,
    },
    "Fleet Register": {"Internal Auditor": _FROZEN},
    "Fuel Claim Register": {
        "Fleet Project Manager": _FROZEN,
        "Fleet Supervisor": _FROZEN,
    },
    "Fuel Consumption Summary": {"Internal Auditor": _FROZEN},
    "Fuel Exception Register": {
        "Fleet Project Manager": _FROZEN,
        "Fleet Supervisor": _FROZEN,
    },
    "Movement Cost Recovery Register": {"Fleet Supervisor": _FROZEN},
    "Movement Cost Summary": {"Fleet Supervisor": _FROZEN},
    "Movement KPI Summary": {
        "Finance Manager": _FROZEN,
        "Fleet Project Manager": _FROZEN,
        "Fleet Supervisor": _FROZEN,
    },
    "Rental Settlement Register": {"Fleet Project Manager": _FROZEN},
    "Transport Fulfilment SLA": {"Finance Manager": _FROZEN},
    "Vehicle Compliance Register": {
        "Finance Manager": _FROZEN,
        "Fleet Project Manager": _FROZEN,
    },
    "Worker Transport Plan": {
        "Finance Manager": _FROZEN,
        "Fleet Supervisor": _FROZEN,
    },
}

# A-171's own decisions: the persona holds no DocPerm on these sources, so the detector
# never raises them. Recorded because "why is the compliance viewer not here?" must have a
# written answer next to the reports it WAS given.
MONEY_REPORTS_EXCLUDED_FROM_GRO = {
    "Rental Settlement Register": "settlement amounts (Accrued/Claimed/Variance Currency)",
    "Rental Cost by Office": "cost totals (Total Accrued/Settled/Outstanding Currency)",
    "Movement Cost Recovery Register": "recovery Amount (Currency)",
    "Cost Recovery Aging": "receivable ageing buckets (Currency)",
    "Movement Cost Summary": "Total Amount / Total Recovered (Currency)",
    "Fleet Payment Register": "payment Amount (Currency)",
}

# A-172's own decisions, same rule one module over: the safety operator holds no DocPerm
# on any cost source, so the detector never raises these either.
MONEY_REPORTS_EXCLUDED_FROM_SAFETY_OFFICER = {
    "Maintenance Aging": "Cost of Repair (Currency)",
    "Custody Damage Register": "Estimated Cost (Currency)",
    "Accommodation Ledger Summary": "Total Site Cost / Employee Daily Share (Currency)",
}


def _load_doctypes():
    """DocType name -> shipped JSON. Shared so this guard and the scope-partition
    guard cannot drift apart on how they read the same files."""
    return shipped_doctypes()


def _child_to_parent(doctypes):
    """Child-table name -> the first DocType that embeds it through a Table field."""
    out = {}
    for name, data in doctypes.items():
        for field in data.get("fields") or []:
            if field.get("fieldtype") not in ("Table", "Table MultiSelect"):
                continue
            options = field.get("options")
            if options in doctypes and doctypes[options].get("istable"):
                out.setdefault(options, name)
    return out


def _permission_source(ref_doctype, doctypes, parents):
    """The DocType whose DocPerms govern a report's rows, or None if not shipped here."""
    if ref_doctype not in doctypes:
        return None
    if doctypes[ref_doctype].get("istable"):
        return parents.get(ref_doctype)
    return ref_doctype


def _read_roles(doctype_name, doctypes):
    """Roles holding a permlevel-0 read DocPerm — frappe's own set_doctype_roles rule."""
    data = doctypes.get(doctype_name) or {}
    return {
        row["role"]
        for row in data.get("permissions") or []
        if row.get("read") and not row.get("permlevel") and row.get("role")
    }


def _shipped_reports():
    """Report name -> (roles named in its child table, ref_doctype), every module.

    Report names are globally unique in Frappe, so keying by name is safe; the guard
    below asserts that rather than assuming it, since a collision would silently drop
    one module's report from the scan.
    """
    out = {}
    for path in sorted(glob.glob(_REPORT_GLOB)):
        with open(path, encoding="utf-8") as fh:
            try:
                data = json.load(fh)
            except json.JSONDecodeError:
                continue
        if not isinstance(data, dict) or data.get("doctype") != "Report":
            continue
        listed = {row["role"] for row in data.get("roles") or [] if row.get("role")}
        out[data["name"]] = (listed, data.get("ref_doctype"))
    return out


def _report_paths_by_name():
    """Report name -> every JSON path declaring it, to catch a cross-module collision."""
    out = {}
    for path in sorted(glob.glob(_REPORT_GLOB)):
        with open(path, encoding="utf-8") as fh:
            try:
                data = json.load(fh)
            except json.JSONDecodeError:
                continue
        if isinstance(data, dict) and data.get("doctype") == "Report":
            out.setdefault(data["name"], []).append(path)
    return out


def _uncovered_pairs(reports, doctypes):
    """{report: {roles that read the source but are absent from its roles table}}.

    Pure over its inputs so the self-test below can drive it with planted data.
    """
    parents = _child_to_parent(doctypes)
    found = {}
    for name, (listed, ref) in reports.items():
        source = _permission_source(ref, doctypes, parents)
        if not source:
            continue
        missing = _read_roles(source, doctypes) - listed - _ALWAYS_PERMITTED
        if missing:
            found[name] = missing
    return found


class TestReportRoleCoverage(unittest.TestCase):
    """Every DocPerm holder on a report's source is in its roles, or frozen with a reason."""

    def setUp(self):
        self.doctypes = _load_doctypes()
        self.reports = _shipped_reports()

    def test_scan_finds_reports_and_doctypes(self):
        self.assertTrue(self.reports, "no report JSON found — the glob broke")
        self.assertTrue(self.doctypes, "no DocType JSON found — the glob broke")
        # One landmark per module, so a glob that silently drops a tree fails here.
        for landmark in ("Vehicle Compliance Register", "Safety Open Findings", "SIM Exceptions"):
            self.assertIn(landmark, self.reports)

    def test_report_names_do_not_collide_across_modules(self):
        """Reports are keyed by name; a duplicate would hide one module's roles table."""
        duplicates = {n: p for n, p in _report_paths_by_name().items() if len(p) > 1}
        self.assertEqual(duplicates, {}, "two modules ship a Report under the same name")

    def test_child_table_ref_resolves_to_its_parent(self):
        """Vehicle Compliance Register reads a child table; its DocPerms live on the parent."""
        parents = _child_to_parent(self.doctypes)
        self.assertTrue(self.doctypes["Salis Vehicle Compliance"].get("istable"))
        self.assertEqual(
            _permission_source("Salis Vehicle Compliance", self.doctypes, parents),
            "Salis Vehicle",
        )

    def test_no_new_uncovered_report_role(self):
        found = {
            report: dict.fromkeys(sorted(roles))
            for report, roles in _uncovered_pairs(self.reports, self.doctypes).items()
        }
        expected = {
            report: dict.fromkeys(sorted(roles))
            for report, roles in KNOWN_REPORT_ROLE_GAPS.items()
        }
        self.assertEqual(
            found,
            expected,
            "report/role coverage changed. A NEW pair means that role reads the source "
            "DocType but the report will not appear on its Reports card (frappe/boot.py "
            "get_user_pages_or_reports) — add it to the report's roles table, or freeze it "
            "here with a written reason. A MISSING pair means a gap was closed and the "
            "baseline must shrink.",
        )

    def test_the_detector_flags_a_removed_role(self):
        """Proof the guard can fail: a role reading the source but absent from the roles
        table must be reported. Driven with synthetic input so it proves the DETECTOR, not
        the current file contents — the file-level proof is the assertion above going red."""
        source_roles = _read_roles("Salis Vehicle", self.doctypes)
        self.assertIn("Internal Auditor", source_roles, "fixture DocType changed shape")
        planted = {"_A171 Planted Report": (source_roles - {"Internal Auditor"}, "Salis Vehicle")}
        found = _uncovered_pairs(planted, self.doctypes)
        self.assertEqual(
            found.get("_A171 Planted Report"),
            {"Internal Auditor"},
            "the detector missed a role removed from a report's roles table",
        )

    def test_every_frozen_pair_carries_a_reason(self):
        for report, roles in KNOWN_REPORT_ROLE_GAPS.items():
            for role, reason in roles.items():
                with self.subTest(report=report, role=role):
                    self.assertTrue(
                        reason and reason.strip(),
                        f"frozen pair {report}/{role} has no documented reason",
                    )


class TestGovernmentRelationsOfficerReportAccess(unittest.TestCase):
    """A-171's own outcome, asserted by name so it cannot be ratcheted away."""

    GRANTED = (
        "Vehicle Compliance Register",
        "Driver Clearance Register",
        "Fleet Register",
    )

    def setUp(self):
        self.reports = _shipped_reports()

    def test_the_persona_reaches_its_compliance_reports(self):
        for name in self.GRANTED:
            with self.subTest(report=name):
                listed, _ref = self.reports[name]
                self.assertIn(
                    GRO_ROLE,
                    listed,
                    f"{name} no longer names {GRO_ROLE}; its Reports card goes empty again",
                )

    def test_the_persona_is_never_frozen_into_the_baseline(self):
        for report, roles in KNOWN_REPORT_ROLE_GAPS.items():
            with self.subTest(report=report):
                self.assertNotIn(
                    GRO_ROLE,
                    roles,
                    "A-171 must stay fixed in the report JSON, never frozen as a known gap",
                )

    def test_money_reports_stay_closed_to_the_persona(self):
        """A compliance-viewer charter does not cover settlement amounts or payments."""
        for name, why in MONEY_REPORTS_EXCLUDED_FROM_GRO.items():
            with self.subTest(report=name):
                self.assertTrue(why.strip(), f"{name} exclusion has no reason")
                listed, _ref = self.reports[name]
                self.assertNotIn(
                    GRO_ROLE,
                    listed,
                    f"{name} exposes {why} — outside the compliance-viewer charter",
                )


class TestSafetyOfficerReportAccess(unittest.TestCase):
    """A-172's own outcome: the safety operator reaches the reports built over its records.

    The charter is READ from docs/training/README.md rather than quoted here. It is what
    puts a Safety Task Execution report inside the persona's remit, so if the published
    wording drops that capability the justification is gone and this class must red rather
    than keep enforcing a rule the page no longer makes.

    The granted set is derived from the shipped report JSON, not listed: every report over
    the source must name the role, so a fourth one added later cannot quietly ship without
    it — the same omission this class was written to catch.
    """

    SOURCE = "Safety Task Execution"

    def setUp(self):
        self.reports = _shipped_reports()
        self.doctypes = _load_doctypes()

    def _reports_over_the_source(self):
        return sorted(name for name, (_l, ref) in self.reports.items() if ref == self.SOURCE)

    def test_the_charter_still_covers_the_source(self):
        charter = role_charters().get(SAFETY_ROLE)
        self.assertIsNotNone(
            charter, f"{SAFETY_ROLE} has no Roles at a glance row in docs/training/README.md"
        )
        self.assertIn(
            SAFETY_CAPABILITY,
            charter,
            f"the published {SAFETY_ROLE} charter no longer names {SAFETY_CAPABILITY!r}, "
            f"which is why reports over {self.SOURCE} are in-charter for it. Restore the "
            f"wording or re-decide the grants. Charter now: {charter!r}",
        )

    def test_the_persona_reads_the_source_it_is_reported_on(self):
        self.assertIn(
            SAFETY_ROLE,
            _read_roles(self.SOURCE, self.doctypes),
            f"{SAFETY_ROLE} lost its read DocPerm on {self.SOURCE}",
        )

    def test_the_persona_reaches_its_safety_reports(self):
        granted = self._reports_over_the_source()
        self.assertGreaterEqual(len(granted), 3, f"no report reads {self.SOURCE} — scan broke")
        for name in granted:
            with self.subTest(report=name):
                listed, _ref = self.reports[name]
                self.assertIn(
                    SAFETY_ROLE,
                    listed,
                    f"{name} no longer names {SAFETY_ROLE}; the report built for the "
                    "safety operator disappears from its Reports card again",
                )

    def test_the_persona_is_never_frozen_into_the_baseline(self):
        for report, roles in KNOWN_REPORT_ROLE_GAPS.items():
            with self.subTest(report=report):
                self.assertNotIn(
                    SAFETY_ROLE,
                    roles,
                    "A-172 must stay fixed in the report JSON, never frozen as a known gap",
                )

    def test_money_reports_stay_closed_to_the_persona(self):
        """A field-operator charter names inspections and incidents, never amounts."""
        for name, why in MONEY_REPORTS_EXCLUDED_FROM_SAFETY_OFFICER.items():
            with self.subTest(report=name):
                self.assertTrue(why.strip(), f"{name} exclusion has no reason")
                listed, _ref = self.reports[name]
                self.assertNotIn(
                    SAFETY_ROLE,
                    listed,
                    f"{name} exposes {why} — outside the field-operator charter",
                )


class TestTheScanCoversEveryModule(unittest.TestCase):
    """A-172's widening, asserted structurally so the glob cannot narrow back to Salis."""

    EXPECTED_MODULES = frozenset({"habitat", "logistay", "salis"})

    def test_every_module_report_tree_is_scanned(self):
        scanned = {
            os.path.relpath(path, _APP).split(os.sep)[0]
            for paths in _report_paths_by_name().values()
            for path in paths
        }
        self.assertEqual(
            scanned,
            self.EXPECTED_MODULES,
            "the report glob no longer covers every module that ships reports",
        )

    def test_logistay_reports_are_clean(self):
        """Recorded as a result, not an assumption: no Logistay report drops a reader."""
        doctypes = _load_doctypes()
        logistay = {
            name
            for name, paths in _report_paths_by_name().items()
            if any(os.path.relpath(p, _APP).split(os.sep)[0] == "logistay" for p in paths)
        }
        self.assertTrue(logistay, "no Logistay report found — the glob broke")
        uncovered = _uncovered_pairs(_shipped_reports(), doctypes)
        self.assertEqual(
            sorted(logistay & set(uncovered)),
            [],
            "a Logistay report now drops a reader; fix it or freeze it with a reason",
        )


if __name__ == "__main__":
    unittest.main()
