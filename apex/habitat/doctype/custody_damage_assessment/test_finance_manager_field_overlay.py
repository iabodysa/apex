# Copyright (c) 2026, AFMCO and contributors
"""The Finance Manager permlevel-1 rows, and the one DocType that also holds permlevel 0.

Five Habitat DocTypes -- Custody Damage Assessment, Housing Checkout, Maintenance
Request, Subcontractor Service Contract, Subcontractor Service Order -- give
``Finance Manager`` a permlevel-1 read+write row. Four of them still ship no
permlevel-0 row at all. Two readings of that shape were possible:

LAYERED  the row is a deliberate FIELD unlock over a document some OTHER role opens.
FLAT     the row is inert, because a role with no permlevel-0 row cannot open the doc.

LAYERED is correct as a matter of framework mechanics, and this module proves it by
replaying the two frappe v15 algorithms against the shipped JSON:

* Document access reads permlevel-0 rows ONLY --
  ``frappe/permissions.py:284`` ``is_perm_applicable`` filters ``cint(perm.permlevel) == 0``.
* Field access is computed SEPARATELY and unions every permlevel across all of the
  user's roles -- ``frappe/model/document.py:808`` ``get_permlevel_access`` and
  ``frappe/model/meta.py:633``. It never consults permlevel-0 access.

So a permlevel-1 row is live for any user holding that role PLUS a role that opens the
document, and the two levels are independent grants -- which is also why a permlevel-1
row is never a duplicate of a permlevel-0 row and dedupe must key on the
(role, permlevel) PAIR.

THE 2026-07-27 DECISION -- Custody Damage Assessment now ALSO carries a permlevel-0
``read`` row for Finance Manager. The omission used to be recorded here as deliberate;
it was then argued on its own evidence and the owner granted it anyway, over three
stated costs: the shipped role profile already pairs Finance Manager with Internal
Auditor, who holds the read, so only a hand-assembled solo finance user lacked it; the
permlevel-1 row unlocks exactly one field while a level-0 read is the WHOLE record,
resident identity included; and Finance Manager is unscoped, so the read spans every
building. ``TestTheGrantedReadIsWhatWasDecided`` keeps that cost visible in the test
instead of only in a decision note. The other four keep the overlay-only shape. On
2026-07-31 that row also gained ``report`` -- ``TestTheReportGrantIsBothHalves`` holds it.

MAINTENANCE REQUEST IS A SECOND EXCEPTION and is asserted separately below: it ships an
``All`` permlevel-0 row (read+create, if_owner), and every logged-in user holds ``All``
(``frappe/permissions.py:520``). A Finance-Manager-only user therefore CAN create one and
populate the financial fields on it. On that DocType the flat "inert" reading is false
outright, with no layering involved.

Run standalone:  python3 -m unittest apex.habitat.doctype.custody_damage_assessment.test_finance_manager_field_overlay -v
"""

from __future__ import annotations

import ast
import json
import os
import unittest

_HABITAT_DOCTYPES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_HABITAT = os.path.dirname(_HABITAT_DOCTYPES)

# Every logged-in user carries these, so a "solo role" test must include them or it
# understates access. frappe/permissions.py:520.
AUTOMATIC_ROLES = frozenset({"All", "Guest", "Desk User"})

# The pattern under guard: DocType -> the non-display fields its permlevel-1 rows unlock.
# Section Breaks are display fieldtypes and are excluded from the value reset
# (frappe/model/base_document.py:1270), so only real data fields are listed.
OVERLAY = {
    "custody_damage_assessment": ("total_estimated_replacement_cost",),
    "housing_checkout": ("cost_center", "damage_deduction_amount", "additional_salary_deduction"),
    "maintenance_request": ("cost_of_repair", "cost_center"),
    "subcontractor_service_contract": ("rate_per_visit", "monthly_retainer"),
    "subcontractor_service_order": ("service_cost",),
}

FINANCE = "Finance Manager"

# The one of the five the 2026-07-27 decision granted a permlevel-0 read on.
GRANTED = "custody_damage_assessment"

# Fields the granted read newly puts in front of Finance Manager. Named so the cost of
# the decision is asserted, not just described: these carry who the damage is charged to.
RESIDENT_IDENTITY = ("party_type", "party", "employee")

# The report the 2026-07-31 grant exists for, and the fields it puts on screen. Held as
# data so the "no new datum" claim is asserted against the shipped report, not described.
REGISTER = "custody_damage_register"
REGISTER_NAME = "Custody Damage Register"
REGISTER_COLUMNS = (
    "name",
    "assessment_date",
    "building",
    "employee",
    "total_estimated_replacement_cost",
    "deduction_entry",
)


def load(slug: str) -> dict:
    path = os.path.join(_HABITAT_DOCTYPES, slug, f"{slug}.json")
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def load_report(slug: str) -> dict:
    path = os.path.join(_HABITAT, "report", slug, f"{slug}.json")
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def columns_in_report_source(slug: str) -> tuple:
    """Fieldnames the shipped Script Report actually returns.

    Parsed with ``ast`` rather than imported, because the report imports frappe and this
    module must stay runnable with no bench. Binding to the source is what stops
    REGISTER_COLUMNS under-covering a column added to the report later -- the recorded
    justification for the 2026-07-31 grant is a claim about the FULL column set.
    """
    path = os.path.join(_HABITAT, "report", slug, f"{slug}.py")
    with open(path, encoding="utf-8") as handle:
        tree = ast.parse(handle.read())
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        for key, value in zip(node.keys, node.values):
            if isinstance(key, ast.Constant) and key.value == "fieldname":
                if isinstance(value, ast.Constant):
                    found.append(value.value)
    return tuple(found)


def report_lists_for(report: dict, roles: set) -> bool:
    """Replay frappe/boot.py get_user_pages_or_reports for the roles-table half.

    A report whose ``roles`` table is non-empty is returned only when one of its rows
    names a role the session holds (boot.py:249-257); the "no role = allowed" branch
    (:275-279) is never reached for such a report.
    """
    listed = {row.get("role") for row in report.get("roles") or [] if row.get("role")}
    if not listed:
        return True
    return bool(listed & roles)


def doc_access(meta: dict, roles: set, ptype: str) -> int:
    """Replay frappe.permissions.get_role_permissions for one ptype.

    Faithful to frappe/permissions.py:283-307: only permlevel-0 rows are applicable,
    and an if_owner-ONLY grant collapses to 0 for every ptype except ``create`` (never
    owner-scoped) and select/read (kept at 1 so the list view can still filter by owner).
    """
    applicable = [
        p for p in meta.get("permissions", [])
        if p.get("role") in roles and int(p.get("permlevel", 0) or 0) == 0
    ]
    has_if_owner = any(p.get("if_owner", 0) for p in applicable)
    value = 1 if any(p.get(ptype, 0) for p in applicable) else 0
    if not value or not has_if_owner or ptype == "create":
        return value
    if any(p.get(ptype, 0) and not p.get("if_owner", 0) for p in applicable):
        return value
    return 1 if ptype in ("select", "read") else 0


def permlevel_access(meta: dict, roles: set, ptype: str) -> set:
    """Replay Document.get_permlevel_access (frappe/model/document.py:808).

    Note what is absent: no permlevel-0 precondition, and no filtering by whether the
    user can open the document. That absence IS the layered reading.
    """
    return {
        int(p.get("permlevel", 0) or 0)
        for p in meta.get("permissions", [])
        if p.get("role") in roles and p.get(ptype, 0)
    }


def visible_fields(meta: dict, roles: set) -> set:
    """Fieldnames surviving apply_fieldlevel_read_permissions (document.py:766-774)."""
    allowed = permlevel_access(meta, roles, "read")
    return {
        f["fieldname"] for f in meta.get("fields", [])
        if not int(f.get("permlevel", 0) or 0) or int(f["permlevel"]) in allowed
    }


def rows_for(meta: dict, role: str) -> dict:
    return {int(p.get("permlevel", 0) or 0): p for p in meta.get("permissions", []) if p.get("role") == role}


class TestThePatternStillShips(unittest.TestCase):
    """Change-detector. Adding a permlevel-0 Finance Manager row to one of these five is
    a document grant, so it may not arrive as a silent side effect of unrelated work.
    Custody Damage Assessment is the one that HAS been argued and granted, on
    2026-07-27; every other slug still has to come through the same door."""

    def test_four_ship_permlevel_one_only_and_the_granted_one_carries_both(self):
        for slug in OVERLAY:
            with self.subTest(slug=slug):
                levels = rows_for(load(slug), FINANCE)
                self.assertEqual(
                    set(levels), {0, 1} if slug == GRANTED else {1},
                    f"{slug}: the Finance Manager permlevel set changed. A new "
                    "permlevel-0 row is a grant of the whole document to an unscoped "
                    "role and needs its own decision; a lost one revokes access "
                    "someone is relying on",
                )
                self.assertTrue(levels[1].get("read"))
                self.assertTrue(levels[1].get("write"))

    def test_overlay_unlocks_exactly_the_recorded_financial_fields(self):
        for slug, expected in OVERLAY.items():
            with self.subTest(slug=slug):
                meta = load(slug)
                high = tuple(
                    f["fieldname"] for f in meta["fields"]
                    if int(f.get("permlevel", 0) or 0) > 0 and "Break" not in f["fieldtype"]
                )
                self.assertEqual(high, expected, f"{slug}: permlevel-1 field set changed")

    def test_openers_carry_both_levels_which_is_why_the_shape_reads_deliberate(self):
        """System Manager and Accommodation Manager open these documents AND hold their
        own permlevel-1 rows. Re-granting at level 1 what they already hold at level 0 is
        only meaningful to an author who knew the two levels are independent -- so the
        Finance Manager row omitting level 0 is a choice, not an oversight."""
        for slug in OVERLAY:
            with self.subTest(slug=slug):
                meta = load(slug)
                for opener in ("System Manager", "Accommodation Manager"):
                    self.assertEqual(
                        set(rows_for(meta, opener)), {0, 1},
                        f"{slug}: {opener} no longer carries both permlevels",
                    )


class TestLayeredNotFlat(unittest.TestCase):

    def test_a_solo_finance_manager_still_cannot_open_three_of_the_five(self):
        """Two are now out of this set for different reasons: Maintenance Request through
        its ``All`` row, Custody Damage Assessment through the 2026-07-27 grant."""
        for slug in OVERLAY:
            if slug in ("maintenance_request", GRANTED):
                continue
            with self.subTest(slug=slug):
                meta = load(slug)
                solo = {FINANCE} | AUTOMATIC_ROLES
                self.assertEqual(doc_access(meta, solo, "read"), 0)
                self.assertEqual(doc_access(meta, solo, "write"), 0)
                self.assertEqual(doc_access(meta, solo, "create"), 0)

    def test_the_row_is_still_a_real_field_grant_for_that_same_user(self):
        """The grant exists at field level even while document access is nil -- which is
        exactly why it is NOT inert: it activates the moment the user is also given an
        opener role, with no DocPerm edit anywhere."""
        for slug in OVERLAY:
            with self.subTest(slug=slug):
                solo = {FINANCE} | AUTOMATIC_ROLES
                self.assertEqual(permlevel_access(load(slug), solo, "write"), {1})

    def test_layering_an_opener_role_makes_the_write_live(self):
        for slug in OVERLAY:
            with self.subTest(slug=slug):
                meta = load(slug)
                layered = {FINANCE, "Accommodation Manager"} | AUTOMATIC_ROLES
                self.assertEqual(doc_access(meta, layered, "write"), 1)
                self.assertIn(1, permlevel_access(meta, layered, "write"))

    def test_shipped_role_profile_makes_the_custody_read_live_today(self):
        """The one case that needs no hypothetical user. The shipped role profile
        ``Habitat Finance Reviewer`` (apex/setup.py) is Finance Manager + Internal
        Auditor. Internal Auditor holds permlevel-0 read on Custody Damage Assessment,
        so that profile opens the document -- and the Currency total is readable ONLY
        because of the Finance Manager permlevel-1 row."""
        meta = load("custody_damage_assessment")
        profile = {FINANCE, "Internal Auditor"} | AUTOMATIC_ROLES
        self.assertEqual(doc_access(meta, profile, "read"), 1)
        self.assertEqual(permlevel_access(meta, profile, "read"), {0, 1})
        self.assertIn("total_estimated_replacement_cost", visible_fields(meta, profile))

        # Guard-of-the-guard: without the Finance Manager row the same profile loses the
        # field. If this assertion ever passes both ways the replay above proves nothing.
        stripped = dict(meta)
        stripped["permissions"] = [p for p in meta["permissions"] if p.get("role") != FINANCE]
        self.assertEqual(doc_access(stripped, profile, "read"), 1)
        self.assertNotIn("total_estimated_replacement_cost", visible_fields(stripped, profile))


class TestTheGrantedReadIsWhatWasDecided(unittest.TestCase):
    """The 2026-07-27 grant and its price, asserted together."""

    def test_a_solo_finance_manager_now_opens_the_record_and_reads_the_resident(self):
        """One method on purpose: the access and what it exposes are the same fact, and
        splitting them lets a reader see the grant without ever meeting its cost."""
        meta = load(GRANTED)
        solo = {FINANCE} | AUTOMATIC_ROLES

        self.assertEqual(
            doc_access(meta, solo, "read"),
            1,
            "the 2026-07-27 grant is gone -- a Finance Manager holding no other role "
            "can no longer open this record",
        )

        # What the read is actually worth: every permlevel-0 field, not merely the money
        # the permlevel-1 row already unlocked. This is the whole record, estate-wide.
        visible = visible_fields(meta, solo)
        for fieldname in RESIDENT_IDENTITY:
            with self.subTest(field=fieldname):
                self.assertIn(
                    fieldname,
                    visible,
                    f"{fieldname} no longer reaches Finance Manager. If the field moved "
                    "behind a permlevel the recorded cost of this grant is now wrong; "
                    "if it was renamed, rename it here too",
                )

        # A read, and after 2026-07-31 the report surface over it. Any OTHER right turning
        # 1 is a widening no one decided. ``report`` is deliberately absent from this list
        # and asserted positively in TestTheReportGrantIsBothHalves instead.
        for ptype in ("write", "create", "submit", "cancel", "delete", "export", "share"):
            with self.subTest(ptype=ptype):
                self.assertEqual(
                    doc_access(meta, solo, ptype),
                    0,
                    f"the grant widened to {ptype}; 2026-07-27 decided a read, and "
                    "2026-07-31 added report and nothing else",
                )


class TestTheReportGrantIsBothHalves(unittest.TestCase):
    """The 2026-07-31 decision: Finance Manager opens Custody Damage Register.

    The 2026-07-27 read let a solo Finance Manager open one assessment from its
    notification but not the register that totals them, because a report is gated TWICE:
    ``frappe.has_permission(ref_doctype, "report")`` when it is opened
    (``frappe/desk/query_report.py:47``), and its ``roles`` child table when it is listed
    (``frappe/boot.py`` ``get_user_pages_or_reports``). Both halves are granted together
    because either alone is a defect -- the DocPerm alone leaves the report invisible, and
    the roles row alone is the live-link-that-throws ``report_role_guard`` refuses on save.

    It is a SURFACE grant, not an access widening. Every register column is permlevel 0 and
    opened by the 2026-07-27 read, except ``total_estimated_replacement_cost``, which is
    permlevel 1 -- this role's OWN overlay field. Rows are unchanged too: Habitat oversight
    is unscoped (``HOUSING_UNSCOPED_ROLES``), so the building filter returns the same rows
    either way. Charter basis (``docs/training/README.md``, Roles at a glance): "Central
    finance control; approves payments, reconciles costs" -- and this is a cost register
    whose last column is the Additional Salary the damage is charged to.
    """

    def setUp(self):
        self.meta = load(GRANTED)
        self.report = load_report(REGISTER)
        self.solo = {FINANCE} | AUTOMATIC_ROLES

    def test_the_report_gate_on_the_source_docperm_passes(self):
        """query_report.py:47 -- frappe.has_permission(ref_doctype, "report")."""
        self.assertEqual(
            doc_access(self.meta, self.solo, "report"),
            1,
            "the 2026-07-31 grant is gone: a solo Finance Manager opening "
            f"{REGISTER_NAME} gets a PermissionError from query_report.py:47",
        )

    def test_the_report_is_listed_for_the_role(self):
        """boot.py get_user_pages_or_reports -- the roles child table."""
        self.assertTrue(
            report_lists_for(self.report, self.solo),
            f"{REGISTER_NAME} no longer names {FINANCE} in its roles table, so the "
            "report never reaches the role's report list however the DocPerm reads",
        )

    def test_neither_half_alone_would_have_been_shippable(self):
        """Negative control for both gates: drop one half at a time and the replay must
        flip. If either assertion above passed with its half removed it proves nothing."""
        without_report_flag = dict(self.meta)
        without_report_flag["permissions"] = [
            {k: (0 if k == "report" else v) for k, v in row.items()}
            if row.get("role") == FINANCE and not int(row.get("permlevel", 0) or 0)
            else row
            for row in self.meta["permissions"]
        ]
        self.assertEqual(
            doc_access(without_report_flag, self.solo, "report"),
            0,
            "the DocPerm replay reports `report` even with the flag cleared",
        )

        unlisted = dict(self.report)
        unlisted["roles"] = [r for r in self.report["roles"] if r.get("role") != FINANCE]
        self.assertFalse(
            report_lists_for(unlisted, self.solo),
            "the roles-table replay lists the report even with the role removed",
        )
        # And the report must still have SOME role, or the empty-table branch would be
        # what made the negative control pass.
        self.assertTrue(unlisted["roles"], "the roles table is empty; the control is vacuous")

    def test_the_register_shows_no_field_the_role_could_not_already_open(self):
        """Why this is a surface grant. Every column is either permlevel 0 -- opened by
        the 2026-07-27 read -- or the permlevel-1 overlay field this role already holds.
        ``name`` is the docname and carries no permlevel."""
        visible = visible_fields(self.meta, self.solo)
        by_name = {f["fieldname"]: f for f in self.meta["fields"]}
        for column in REGISTER_COLUMNS:
            with self.subTest(column=column):
                if column == "name":
                    continue
                self.assertIn(column, by_name, f"{column} is no longer a field on {GRANTED}")
                self.assertIn(
                    column,
                    visible,
                    f"{column} is on {REGISTER_NAME} but is NOT readable by a solo "
                    f"{FINANCE}. The 2026-07-31 grant was justified on the register "
                    "exposing nothing new; that justification is now false",
                )

    def test_the_column_list_still_matches_the_shipped_report(self):
        """Keeps the check above honest. A column added to the report but not here would
        never be tested for readability, and the grant's justification would rot unseen."""
        self.assertEqual(
            columns_in_report_source(REGISTER),
            REGISTER_COLUMNS,
            f"{REGISTER_NAME} returns a different column set than REGISTER_COLUMNS "
            "records. Update the tuple, then check the new column is readable by a solo "
            f"{FINANCE} -- if it is not, the 2026-07-31 grant needs revisiting",
        )

    def test_the_money_column_is_the_overlay_field_and_not_a_second_grant(self):
        """The one column that needed permlevel-1 access is the field the top of this
        module is about, so the report grant leans on the existing overlay row."""
        self.assertIn("total_estimated_replacement_cost", OVERLAY[GRANTED])
        self.assertIn(1, permlevel_access(self.meta, self.solo, "read"))


class TestMaintenanceRequestIsTheOtherExceptionOfTheFive(unittest.TestCase):
    """The two readings agree on three DocTypes and disagree on this one, and they
    disagree on it without any grant having been made.

    Maintenance Request ships an ``All`` permlevel-0 row (read+create, if_owner). Every
    logged-in user holds ``All``, so a Finance-Manager-only user reaches permlevel-0
    ``create`` with no layering at all -- if_owner never restricts ``create``
    (frappe/permissions.py:301). Their permlevel-1 write then survives
    validate_higher_perm_levels, so the repair cost they type is kept rather than reset.
    The row is therefore live for a solo Finance Manager here, and the flat reading is
    false on this DocType for a different reason than on the other four."""

    def setUp(self):
        self.meta = load("maintenance_request")
        self.solo = {FINANCE} | AUTOMATIC_ROLES

    def test_the_all_row_is_what_makes_this_one_different(self):
        row = rows_for(self.meta, "All")
        self.assertEqual(set(row), {0})
        self.assertTrue(row[0].get("if_owner"), "the All row is no longer owner-scoped")
        self.assertTrue(row[0].get("create"))
        self.assertFalse(row[0].get("write"), "an All write row would be a far bigger grant")

    def test_solo_finance_manager_can_create_but_not_edit(self):
        self.assertEqual(doc_access(self.meta, self.solo, "create"), 1)
        self.assertEqual(doc_access(self.meta, self.solo, "write"), 0)
        self.assertEqual(doc_access(self.meta, self.solo, "submit"), 0)

    def test_and_the_money_fields_stick_on_that_created_draft(self):
        """reset_values_if_no_permlevel_access resets only fields whose permlevel is NOT
        in the user's write set (base_document.py:1265-1273). Permlevel 1 IS in it."""
        allowed = permlevel_access(self.meta, self.solo, "write")
        for fieldname in OVERLAY["maintenance_request"]:
            self.assertIn(
                int(next(f for f in self.meta["fields"] if f["fieldname"] == fieldname)["permlevel"]),
                allowed,
            )


class TestTheReasonIsRecordedBesideThePattern(unittest.TestCase):
    """The reason must live with the rows, not only here. A DocType JSON cannot carry a
    comment, so each controller docstring holds it; this asserts none of the five loses
    it in a later edit."""

    MARKER = "permlevel-1"

    def test_every_controller_docstring_records_it(self):
        for slug in OVERLAY:
            with self.subTest(slug=slug):
                path = os.path.join(_HABITAT_DOCTYPES, slug, f"{slug}.py")
                with open(path, encoding="utf-8") as handle:
                    head = handle.read(2400)
                # The board id this used to also assert is deliberately gone: a card
                # reference means nothing to a reader without the board, and pinning
                # one here blocked draining it from the five docstrings.
                self.assertIn(self.MARKER, head, f"{slug}: permlevel reason no longer recorded")


if __name__ == "__main__":
    unittest.main()
