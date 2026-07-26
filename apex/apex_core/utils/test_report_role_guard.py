# Copyright (c) 2026, AFMCO and contributors
"""A-201 — the Report ``validate`` hook that refuses an unrunnable role.

Pure-Python against a stubbed frappe, so the refusal is proven with no live site: the
shared bench was closed to writes for this wave, and the guard's whole job is to make a
``doc.save()`` fail, which cannot be demonstrated read-only. A live demonstration is
therefore still OWED — everything below drives ``report_role_guard.validate`` with a
constructed document instead of a saved one.

The stub is deliberately narrow: it answers only the four things the hook asks frappe
(the ref's module, the module's owning app, the ref's meta, and the migration flags) and
records what the hook did (throw / msgprint). Every test patches
``report_role_guard.frappe`` with it, so the same assertions hold whether the real frappe
is importable or not — which is what makes the documented standalone command honest.

Four properties, matching the card's proofs:

1. REFUSED — a role its ``ref_doctype`` denies is thrown on, and the message names both
   the role and the ref_doctype. Driven for all four denial shapes (no row, permlevel
   above 0, ``report`` unset, ``if_owner``-only) plus the child-table ref.
2. ALLOWED — a role whose ref DOES grant ``report`` saves with nothing raised and
   nothing printed. Without this control a hook that refused everything would look right.
3. THE APP'S OWN REPORTS STILL SAVE — every shipped Report JSON is replayed through the
   hook as both the incoming and the stored document, and none of them throws. A-211 took
   ``KNOWN_UNRUNNABLE_REPORT_ROLES`` from seven entries to three; the three that remain
   are one unresolved question, not three, and they warn instead of throwing, which is
   exactly the pre-existing-row clause. The set stays exact-equality, so a NEW offender
   fails the build rather than being absorbed.
4. THE DETECTOR CAN FAIL — every clause has a control that must stay clean, and
   ``test_removing_the_report_flag_check_lets_the_offender_through`` reproduces the
   guard with that one clause deleted and asserts it goes blind.

Also proven here, because they are the two ways this hook could do damage:
``TestAMigrateIsNeverAborted`` (no throw under any migration flag) and
``TestAPreExistingRoleDoesNotBrickAnEdit`` (no throw for a role already stored).

THE A-211 DRAIN — four of the seven entries resolved
----------------------------------------------------
All seven frozen entries reached their role through the Reports list and the awesomebar
(``boot.get_user_pages_or_reports``) rather than a workspace card, which is why A-200's
workspace sweep never saw them. Each was judged on its own evidence rather than flattened
by a blanket grant. Both roles involved are named in ``habitat/permissions.py``
``HOUSING_UNSCOPED_ROLES`` and ``salis/permissions.py`` ``UNSCOPED_ROLES``, and all seven
reports re-apply that scope themselves in Python, so no grant below lifts a row filter the
role was actually held behind — the usual "a Script Report bypasses
permission_query_conditions" hazard does not fire for these two roles.

GRANTED ``report`` on the ref, because the role's own charter already demanded it and the
record carries no personal data:

* ``Facility Asset Movement`` / ``Finance Manager`` — read+report at permlevel 0. The
  DocType ships an ``accounting_acknowledged``/``accounting_acknowledged_by`` gate, and
  the controller refuses to submit an Intercompany Permanent movement that is not
  acknowledged, so an accounting sign-off is enforced on this document. A-218 later
  dropped the "(Finance)" parenthetical from that field's label, because the role holds
  no write here and so was never the one closing the gate; that narrows the label, not
  this read-only grant.
* ``Operational Depreciation Snapshot`` / ``Finance Manager`` — read+report at permlevel
  0. Book values over ``Custody Article``, carrying no personal data; the role already
  reports on both sibling snapshots (Occupancy, Vehicle Utilisation) and on the whole
  Habitat cost surface.
* ``Fuel Daily Log`` / ``Finance Manager`` — ``report`` added to the row it already held.
  The role reports on 5 of the 6 Fuel DocTypes it touches and uniquely holds ``write``
  here; the grant widens no row and no field, only the list/report view.

DROPPED from the report instead, because a grant would have been a real widening:

* ``Custody Damage Register`` / ``Finance Manager``. The role's only row on Custody Damage
  Assessment is permlevel 1, read+write over exactly ``total_estimated_replacement_cost``
  — a layered field unlock on a document another role opens, not a document grant, because
  ``is_perm_applicable`` keeps only permlevel-0 rows (frappe/permissions.py:283-284), so
  the role cannot open that document at all. A permlevel-0 row would have handed it the
  damaged ``items``, ``remarks`` and the ``deduction_entry`` payroll link, none of which
  it reaches today.

  A-279 CORRECTS a second clause this entry used to carry — "it holds no permlevel-0 row
  anywhere else in the custody domain" — which was FALSE, and false in the direction that
  stops the next reader looking. Accommodation Stock Ledger grants Finance Manager
  read+report+export+print+email+share at permlevel 0, the role is named in
  ``habitat/permissions.py`` ``HOUSING_UNSCOPED_ROLES``, and
  ``accommodation_stock_ledger_query`` therefore returns "" — no row filter, every
  building. That ledger carries ``employee`` ("Employee (Custodian)"), ``signed_qty`` and
  ``unit_cost`` at permlevel 0, the exact inputs of ``Custody Outstanding by Worker``,
  whose ``value_sar`` column is computed as balance x unit cost rather than stored. So the
  custodian and the per-person custody value ARE readable and exportable estate-wide
  today; what the dropped grant withheld is the damage-assessment record, not the custody
  holding. Whether a finance role should hold that ledger read is the owner's call, and it
  is not decided in a report's roles table: the roles table only clears
  ``Report.is_permitted`` (query_report.py:41), while the scope lives in the DocPerm row
  and in ``HOUSING_UNSCOPED_ROLES``.

STILL FROZEN — the three Housing Assignment reports, which are ONE question
---------------------------------------------------------------------------
``Accommodation Occupancy Summary``, ``Active Resident Register`` and ``Idle Resident
Detection`` all name ``Internal Auditor`` over the same ref, so the three entries stand or
fall together on a single decision about one DocPerm row. That decision is the owner's:
Housing Assignment ships no permlevel-1 section, so any permlevel-0 read of it is a read
of the WHOLE record — resident identity, the check-in signature and free-text notes,
estate-wide, for a role that holds nothing on that DocType today. This file records what
is observably true about the gap and deliberately does not name a remedy; see the reason
string on the entries themselves.

Run standalone:  python3 -m unittest apex.apex_core.utils.test_report_role_guard -v
"""

import glob
import json
import os
import sys
import types
import unittest
from unittest import mock

# [#a201stb] Same stubbing idiom as apex_core/utils/test_guarded_index_dedupe.py: use the
# real frappe under bench, otherwise stand up the bare module so the import below
# resolves. Nothing is read off it — every test patches the module's `frappe` name.
if "frappe" not in sys.modules:
    sys.modules["frappe"] = types.ModuleType("frappe")

from apex.apex_core.utils import report_role_guard  # noqa: E402
from apex.tests.shipped_doctypes import APP_ROOT, shipped_doctypes  # noqa: E402

_REPORT_GLOB = os.path.join(APP_ROOT, "*", "report", "*", "*.json")

REF = "_A201 Source"
REPORT_ROLE = "_A201 Role"
OTHER_ROLE = "_A201 Other Role"

# An OBSERVATION, not an instruction. It states what is true about the gap and stops there,
# because the remedy is a personnel-data decision reserved to the owner — a reason string
# that names a fix is read by the next agent as a work order and gets executed.
_OWNER_DECISION_HOUSING = (
    "Observed, not prescribed — do NOT act on this entry from this file. Internal Auditor "
    "is named in habitat/permissions.py HOUSING_UNSCOPED_ROLES, so Housing Assignment's "
    "building-scope exemption already covers this role while it holds no DocPerm row on "
    "that DocType for the exemption to apply to. The role reaches these reports through "
    "the Reports list and the awesomebar (boot.get_user_pages_or_reports) rather than a "
    "workspace card, which is why the A-200 workspace sweep never saw them, and "
    "query_report.py:47 refuses the report on open. Housing Assignment ships no "
    "permlevel-1 section, so a permlevel-0 read of it is a read of the entire record: "
    "resident identity (party, employee, employee_name), room_condition_snapshot, "
    "terms_signature and free-text notes, across every building. Whether this role should "
    "hold that is a personnel-data decision for the owner, not a technical gap for an "
    "agent to close; all three entries turn on the same single DocPerm row."
)

# Exact equality, like the sibling baselines. Each entry is (ref_doctype, [roles], reason);
# a new offender fails the build, a repaired one must be pruned. A-211 resolved four of the
# original seven — see "THE A-211 DRAIN" in the module docstring for each call.
KNOWN_UNRUNNABLE_REPORT_ROLES = {
    "Accommodation Occupancy Summary": (
        "Housing Assignment",
        ["Internal Auditor"],
        _OWNER_DECISION_HOUSING,
    ),
    "Active Resident Register": (
        "Housing Assignment",
        ["Internal Auditor"],
        _OWNER_DECISION_HOUSING,
    ),
    "Idle Resident Detection": (
        "Housing Assignment",
        ["Internal Auditor"],
        _OWNER_DECISION_HOUSING,
    ),
}


class Refused(Exception):
    """What the stub raises in place of frappe.throw's ValidationError."""


def _scrub(txt):
    """frappe.scrub, reproduced so the stub needs no frappe."""
    return txt.replace(" ", "_").replace("-", "_").lower()


class FrappeStub:
    """The four questions report_role_guard asks frappe, and a log of what it did."""

    def __init__(self, doctypes, *, owner_app="apex", flags=None):
        self.doctypes = doctypes
        self.owner_app = owner_app
        self.flags = dict(flags or {})
        self.local = types.SimpleNamespace(
            module_app={_scrub(d.get("module") or "Habitat"): owner_app for d in doctypes.values()}
        )
        self.db = types.SimpleNamespace(get_value=self._get_value)
        self.thrown = []
        self.printed = []
        self.meta_reads = []

    scrub = staticmethod(_scrub)

    def _get_value(self, doctype, name, field):
        assert (doctype, field) == ("DocType", "module"), (doctype, field)
        return (self.doctypes.get(name) or {}).get("module")

    def get_meta(self, doctype):
        self.meta_reads.append(doctype)
        data = self.doctypes[doctype]
        return types.SimpleNamespace(
            permissions=data.get("permissions") or [], istable=data.get("istable") or 0
        )

    def _(self, msg):
        return msg

    def throw(self, msg, title=None):
        self.thrown.append(msg)
        raise Refused(msg)

    def msgprint(self, msg, title=None, indicator=None):
        self.printed.append(msg)


class ReportDoc(dict):
    """A Report document carrying only what the hook reads off it."""

    def __init__(self, ref_doctype, roles, stored=None):
        super().__init__(ref_doctype=ref_doctype, roles=[{"role": r} for r in roles])
        self.stored = stored

    def get_doc_before_save(self):
        return None if self.stored is None else ReportDoc(self["ref_doctype"], self.stored)


def _doctype(permission_rows, *, istable=0, module="Habitat"):
    return {REF: {"module": module, "istable": istable, "permissions": list(permission_rows)}}


def _save(stub, doc):
    """Run the hook exactly as frappe's doc_events composer would."""
    with mock.patch.object(report_role_guard, "frappe", stub):
        report_role_guard.validate(doc)


def _read_json(path):
    with open(path, encoding="utf-8") as fh:
        try:
            return json.load(fh)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}


def shipped_reports():
    """Report name -> its shipped JSON, every module's report tree."""
    loaded = (_read_json(path) for path in sorted(glob.glob(_REPORT_GLOB)))
    return {
        data["name"]: data
        for data in loaded
        if isinstance(data, dict) and data.get("doctype") == "Report" and data.get("name")
    }


class TestARoleTheRefDeniesIsRefused(unittest.TestCase):
    """Proof 1 — the save is refused, and the message names role and ref_doctype."""

    def _refusal(self, permission_rows, *, istable=0, roles=(REPORT_ROLE,)):
        stub = FrappeStub(_doctype(permission_rows, istable=istable))
        with self.assertRaises(Refused) as caught:
            _save(stub, ReportDoc(REF, list(roles)))
        return stub, str(caught.exception)

    def test_a_ref_that_omits_the_report_flag_refuses_the_save(self):
        _stub, message = self._refusal([{"role": REPORT_ROLE, "read": 1}])
        self.assertIn(REPORT_ROLE, message, "the refusal does not name the role")
        self.assertIn(REF, message, "the refusal does not name the ref_doctype")
        self.assertIn("report", message)

    def test_a_ref_with_no_row_for_the_role_refuses_the_save(self):
        _stub, message = self._refusal([{"role": OTHER_ROLE, "read": 1, "report": 1}])
        self.assertIn(REPORT_ROLE, message)
        self.assertIn(REF, message)

    def test_a_report_grant_above_permlevel_zero_refuses_the_save(self):
        """permissions.py:284 discards every row whose permlevel is not 0."""
        _stub, message = self._refusal(
            [{"role": REPORT_ROLE, "read": 1, "report": 1, "permlevel": 1}]
        )
        self.assertIn(REPORT_ROLE, message)

    def test_an_if_owner_only_report_grant_refuses_the_save(self):
        """permissions.py:297-307 rewrites `report` back to 0 for an if_owner-only grant."""
        _stub, message = self._refusal(
            [{"role": REPORT_ROLE, "read": 1, "report": 1, "if_owner": 1}]
        )
        self.assertIn(REPORT_ROLE, message)

    def test_a_child_table_ref_refuses_every_role_however_generous_the_row(self):
        """has_permission routes an istable ref into has_child_permission, which denies
        without a parent_doctype (permissions.py:120, :785) and query_report supplies none."""
        _stub, message = self._refusal(
            [{"role": REPORT_ROLE, "read": 1, "report": 1}], istable=1
        )
        self.assertIn(REPORT_ROLE, message)

    def test_the_refusal_names_every_offending_role(self):
        _stub, message = self._refusal(
            [{"role": REPORT_ROLE, "read": 1}], roles=(REPORT_ROLE, OTHER_ROLE)
        )
        self.assertIn(REPORT_ROLE, message)
        self.assertIn(OTHER_ROLE, message)


class TestALegitimateReportStillSaves(unittest.TestCase):
    """Proof 2 — the control. A hook that refused everything would pass proof 1 too."""

    def _clean_save(self, doctypes, doc):
        stub = FrappeStub(doctypes)
        _save(stub, doc)
        self.assertEqual(stub.thrown, [], "a legitimate save was refused")
        self.assertEqual(stub.printed, [], "a legitimate save was warned about")
        return stub

    def test_a_role_whose_ref_grants_report_saves_cleanly(self):
        self._clean_save(
            _doctype([{"role": REPORT_ROLE, "read": 1, "report": 1}]),
            ReportDoc(REF, [REPORT_ROLE]),
        )

    def test_a_plain_row_beside_an_if_owner_row_saves_cleanly(self):
        """Control for the if_owner clause: a non-if_owner grant survives the sibling."""
        self._clean_save(
            _doctype(
                [
                    {"role": REPORT_ROLE, "read": 1, "report": 1, "if_owner": 1},
                    {"role": REPORT_ROLE, "read": 1, "report": 1},
                ]
            ),
            ReportDoc(REF, [REPORT_ROLE]),
        )

    def test_an_empty_roles_table_saves_cleanly(self):
        """A role-less report is open to everyone and names nobody to refuse."""
        self._clean_save(_doctype([{"role": OTHER_ROLE, "read": 1}]), ReportDoc(REF, []))

    def test_administrator_is_never_refused(self):
        """Administrator short-circuits every permission check (permissions.py:107)."""
        self._clean_save(_doctype([]), ReportDoc(REF, ["Administrator"]))


class TestTheHookStaysOutOfOtherApps(unittest.TestCase):
    """A doc_events hook on Report fires for erpnext and hrms too; this one must no-op."""

    def test_a_ref_owned_by_another_app_is_not_judged(self):
        stub = FrappeStub(_doctype([{"role": REPORT_ROLE, "read": 1}]), owner_app="hrms")
        _save(stub, ReportDoc(REF, [REPORT_ROLE]))
        self.assertEqual(stub.thrown, [])
        self.assertEqual(stub.printed, [])
        self.assertEqual(
            stub.meta_reads, [], "the hook read the meta of a DocType apex does not own"
        )

    def test_a_ref_that_resolves_to_no_module_is_not_judged(self):
        stub = FrappeStub({})
        _save(stub, ReportDoc("Salary Slip", [REPORT_ROLE]))
        self.assertEqual((stub.thrown, stub.printed, stub.meta_reads), ([], [], []))

    def test_a_report_with_no_ref_doctype_is_not_judged(self):
        stub = FrappeStub(_doctype([]))
        _save(stub, ReportDoc(None, [REPORT_ROLE]))
        self.assertEqual((stub.thrown, stub.printed, stub.meta_reads), ([], [], []))


class TestAMigrateIsNeverAborted(unittest.TestCase):
    """The blocker A-201 had to clear before the hook could be written at all.

    Module JSON never reaches validate (import_file.py:233-237 sets ignore_validate and
    document.py:1139-1140 returns on it), but sync_fixtures imports with
    ``data_import=True``, which leaves validate ON in the middle of a migrate
    (data_import.py:289-291, migrate.py:143), and a patch that saves a Report is the same
    shape. So the flags are checked directly rather than inferred.
    """

    def test_no_migration_context_throws(self):
        for flag in report_role_guard._MIGRATION_FLAGS:
            with self.subTest(flag=flag):
                stub = FrappeStub(
                    _doctype([{"role": REPORT_ROLE, "read": 1}]), flags={flag: True}
                )
                _save(stub, ReportDoc(REF, [REPORT_ROLE]))
                self.assertEqual(stub.thrown, [], f"the hook threw while {flag} was set")
                self.assertEqual(len(stub.printed), 1, "the offender was silently dropped")
                self.assertIn(REPORT_ROLE, stub.printed[0])

    def test_the_same_save_outside_a_migration_does_throw(self):
        """Control: the flag is what spares it, not a hook that never fires."""
        stub = FrappeStub(_doctype([{"role": REPORT_ROLE, "read": 1}]))
        with self.assertRaises(Refused):
            _save(stub, ReportDoc(REF, [REPORT_ROLE]))


class TestAPreExistingRoleDoesNotBrickAnEdit(unittest.TestCase):
    """A site holding a non-conforming row must still be able to edit that report."""

    def test_an_already_stored_offender_only_warns(self):
        stub = FrappeStub(_doctype([{"role": REPORT_ROLE, "read": 1}]))
        _save(stub, ReportDoc(REF, [REPORT_ROLE], stored=[REPORT_ROLE]))
        self.assertEqual(stub.thrown, [], "an unrelated edit to a legacy report was blocked")
        self.assertEqual(len(stub.printed), 1)

    def test_a_role_added_beside_a_stored_offender_still_throws(self):
        stub = FrappeStub(_doctype([{"role": REPORT_ROLE, "read": 1}]))
        with self.assertRaises(Refused) as caught:
            _save(stub, ReportDoc(REF, [REPORT_ROLE, OTHER_ROLE], stored=[REPORT_ROLE]))
        self.assertIn(OTHER_ROLE, str(caught.exception))

    def test_a_brand_new_report_has_nothing_stored_so_every_offender_throws(self):
        """Report.set_doctype_roles (report.py:107-112) seeds a new report's roles from
        every permlevel-0 row with no look at `report`, so this is the default path."""
        stub = FrappeStub(_doctype([{"role": REPORT_ROLE, "read": 1}]))
        with self.assertRaises(Refused):
            _save(stub, ReportDoc(REF, [REPORT_ROLE], stored=None))


class TestTheAppsOwnReportsStillSave(unittest.TestCase):
    """Proof 3 — replay every shipped Report JSON through the hook."""

    def setUp(self):
        self.doctypes = shipped_doctypes()
        self.reports = shipped_reports()

    def _stub(self):
        return FrappeStub(self.doctypes)

    @staticmethod
    def _roles(report):
        return [row["role"] for row in report.get("roles") or [] if row.get("role")]

    def test_the_scan_sees_the_shipped_tree(self):
        self.assertTrue(self.reports, "no report JSON found — the glob broke")
        self.assertTrue(self.doctypes, "no DocType JSON found — the loader broke")
        pairs = sum(len(self._roles(report)) for report in self.reports.values())
        self.assertGreaterEqual(pairs, 150, f"only {pairs} report/role pairs — the scan broke")

    def test_no_shipped_report_is_refused_on_save(self):
        """As they exist on disk every named role is already stored, so the pre-existing
        clause spares them — a migrate-installed site can re-save any of them."""
        for name, report in sorted(self.reports.items()):
            roles = self._roles(report)
            with self.subTest(report=name):
                stub = self._stub()
                _save(stub, ReportDoc(report.get("ref_doctype"), roles, stored=roles))
                self.assertEqual(stub.thrown, [], f"{name} would be refused on save")

    def test_adding_a_shipped_report_role_back_is_still_checked(self):
        """The same reports with nothing stored: the ratchet of what actually offends."""
        found = {}
        for name, report in self.reports.items():
            ref = report.get("ref_doctype")
            if ref not in self.doctypes:
                continue
            data = self.doctypes[ref]
            denied = report_role_guard.denied_roles(
                data.get("permissions") or [], data.get("istable") or 0, self._roles(report)
            )
            if denied:
                found[name] = (ref, denied)
        expected = {name: (ref, roles) for name, (ref, roles, _why) in
                    KNOWN_UNRUNNABLE_REPORT_ROLES.items()}
        self.assertEqual(
            found,
            expected,
            "shipped report/role runnability changed. A NEW entry means that role is "
            "handed the report by boot.get_user_pages_or_reports and then refused by "
            "query_report.py:47 on open — grant `report` on the ref_doctype row it "
            "already holds, or drop the role from the report's roles table. A MISSING "
            "entry means one was repaired and this baseline must shrink to match.",
        )

    def test_every_frozen_entry_carries_a_reason(self):
        for name, (_ref, roles, why) in KNOWN_UNRUNNABLE_REPORT_ROLES.items():
            with self.subTest(report=name):
                self.assertTrue(roles, f"{name} is frozen with no role named")
                self.assertTrue(why and why.strip(), f"{name} is frozen with no reason")

    def test_no_frozen_entry_names_a_report_that_stopped_shipping(self):
        phantom = sorted(set(KNOWN_UNRUNNABLE_REPORT_ROLES) - set(self.reports))
        self.assertEqual(phantom, [], "the baseline names report(s) this app no longer ships")


class TestTheDetectorCanFail(unittest.TestCase):
    """Proof 4 — reproduce the predicate with the check removed and watch it go blind."""

    ROWS = [{"role": REPORT_ROLE, "read": 1}]

    def test_the_check_present_refuses(self):
        self.assertEqual(
            report_role_guard.denied_roles(self.ROWS, 0, [REPORT_ROLE]), [REPORT_ROLE]
        )

    def test_removing_the_report_flag_check_lets_the_offender_through(self):
        """The mutant: `report` no longer required, exactly the reading A-189 disproved
        (DocPerm.report defaults to 1 in frappe's JSON, but import_file never applies a
        field default, so an omitted flag really is 0)."""
        blind = {
            row["role"]
            for row in self.ROWS
            if row.get("role") and not row.get("if_owner") and not int(row.get("permlevel") or 0)
        }
        self.assertEqual(
            sorted({REPORT_ROLE} - blind),
            [],
            "the mutant still refuses, so this file is not proving the report clause",
        )


if __name__ == "__main__":
    unittest.main()
