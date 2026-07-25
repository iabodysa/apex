# Copyright (c) 2026, AFMCO and contributors
"""A-171 — a DocPerm holder that is absent from a Report's ``roles`` sees an empty card.

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
correspondence for the shipped Salis reports, allowing a report to hold MORE roles than
its source DocType (a curated audience) but never to silently drop one.

Child-table ``ref_doctype`` (Vehicle Compliance Register reads ``Salis Vehicle
Compliance``) resolves to the embedding parent, because a child table carries no DocPerms
of its own and its rows are governed by the parent's.

Scope: Salis only. The Habitat/Logistay reports carry the same gap shape and are a
follow-up; extending the glob here is the whole change needed.

Run standalone:  python3 -m unittest apex.salis.report.test_report_role_coverage -v
"""

import glob
import json
import os
import unittest

_REPORT_DIR = os.path.dirname(os.path.abspath(__file__))
_APP = os.path.normpath(os.path.join(_REPORT_DIR, "..", ".."))
_SALIS_REPORT_GLOB = os.path.join(_REPORT_DIR, "*", "*.json")
_DOCTYPE_GLOB = os.path.join(_APP, "*", "doctype", "*", "*.json")

GRO_ROLE = "Government Relations Officer"

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

KNOWN_REPORT_ROLE_GAPS = {
    # Frozen baseline of role -> reason, per report. The assertion is exact equality: a NEW
    # pair fails the build and a CLOSED pair fails until it is pruned from here.
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


def _load_doctypes():
    """DocType name -> shipped JSON, for every DocType in the app."""
    out = {}
    for path in sorted(glob.glob(_DOCTYPE_GLOB)):
        with open(path, encoding="utf-8") as fh:
            try:
                data = json.load(fh)
            except json.JSONDecodeError:
                continue
        if isinstance(data, dict) and data.get("doctype") == "DocType" and data.get("name"):
            out[data["name"]] = data
    return out


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


def _salis_reports():
    """Report name -> (roles named in its child table, ref_doctype)."""
    out = {}
    for path in sorted(glob.glob(_SALIS_REPORT_GLOB)):
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


class TestSalisReportRoleCoverage(unittest.TestCase):
    """Every DocPerm holder on a report's source is in its roles, or frozen with a reason."""

    def setUp(self):
        self.doctypes = _load_doctypes()
        self.reports = _salis_reports()

    def test_scan_finds_reports_and_doctypes(self):
        self.assertTrue(self.reports, "no Salis report JSON found — the glob broke")
        self.assertTrue(self.doctypes, "no DocType JSON found — the glob broke")
        self.assertIn("Vehicle Compliance Register", self.reports)

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
        self.reports = _salis_reports()

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


if __name__ == "__main__":
    unittest.main()
