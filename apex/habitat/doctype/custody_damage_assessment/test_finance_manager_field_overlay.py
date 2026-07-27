# Copyright (c) 2026, AFMCO and contributors
"""A-218: the Finance Manager permlevel-1 rows that ship WITHOUT a permlevel-0 companion.

Five Habitat DocTypes -- Custody Damage Assessment, Housing Checkout, Maintenance
Request, Subcontractor Service Contract, Subcontractor Service Order -- give
``Finance Manager`` a permlevel-1 read+write row and no permlevel-0 row at all. Two
readings were possible and the pattern carried no recorded reason:

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

The shipped evidence that the shape is deliberate rather than an omission: on all five,
the two roles that DO open the document (System Manager, Accommodation Manager) carry
their own permlevel-1 rows ALONGSIDE their permlevel-0 rows. Whoever wrote these knew
permlevel-0 write does not imply permlevel-1 write and re-granted it explicitly. Finance
Manager is the same construct with the opener half deliberately withheld: it may see and
set the money, it may not open, create, submit or cancel the document.

MAINTENANCE REQUEST IS THE ONE EXCEPTION and is asserted separately below: it ships an
``All`` permlevel-0 row (read+create, if_owner), and every logged-in user holds ``All``
(``frappe/permissions.py:520``). A Finance-Manager-only user therefore CAN create one and
populate the financial fields on it. On that DocType the flat "inert" reading is false
outright, with no layering involved.

Run standalone:  python3 -m unittest apex.habitat.doctype.custody_damage_assessment.test_finance_manager_field_overlay -v
"""

from __future__ import annotations

import json
import os
import unittest

_HABITAT_DOCTYPES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

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


def load(slug: str) -> dict:
    path = os.path.join(_HABITAT_DOCTYPES, slug, f"{slug}.json")
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


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
    """Change-detector. If a later wave normalises one of these five by adding a
    permlevel-0 Finance Manager row, that is a document grant and must be argued for
    on its own evidence -- it must not arrive as a silent side effect."""

    def test_all_five_ship_permlevel_one_only(self):
        for slug in OVERLAY:
            with self.subTest(slug=slug):
                levels = rows_for(load(slug), FINANCE)
                self.assertEqual(
                    set(levels), {1},
                    f"{slug}: Finance Manager rows are no longer permlevel-1-only",
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

    def test_a_solo_finance_manager_cannot_open_four_of_the_five(self):
        for slug in OVERLAY:
            if slug == "maintenance_request":
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


class TestMaintenanceRequestIsTheExceptionOfTheFive(unittest.TestCase):
    """The two readings agree on four DocTypes and disagree on this one.

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
