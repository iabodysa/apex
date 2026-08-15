# Copyright (c) 2026, AFMCO and contributors
"""the acknowledgement gate and the label above it must name the same people.

THE DEFECT. ``accounting_acknowledged_by`` shipped labelled "Acknowledged By (Finance)"
while ``Finance Manager`` held no write on the DocType, and ``_validate_intercompany_gates``
refuses to submit an Intercompany Permanent movement whose ``accounting_acknowledged`` is
unset. So an enforced gate advertised a role that could not reach it, and in practice it
was closed by whoever held System Manager.

WHAT SHIPPED. Both halves were fixed. The label lost its parenthetical, matching its two
sibling Link-to-User fields in the same section, AND the narrow permission shape was built:
the two acknowledgement fields moved BEHIND permlevel 1 and Finance Manager gained a
permlevel-1 read+write row beside its permlevel-0 read row.

WHY FINANCE MANAGER NEEDS BOTH ROWS. Document access resolves from permlevel-0 rows ONLY
(``frappe/permissions.py`` ``is_perm_applicable`` filters ``cint(perm.permlevel) == 0``),
while field access is a separate computation that unions every permlevel the user's roles
hold. A permlevel-1 row alone would leave Finance Manager unable to OPEN the record it is
meant to acknowledge, so the permlevel-0 ``read`` is what lets them reach the form and the
permlevel-1 ``write`` is what lets them tick the flag on it.

WHY THE THREE PERMLEVEL-0 WRITERS DID NOT LOSE THE FLAG. ``validate_higher_perm_levels``
resets high-permlevel fields on save for any user without that level, which would have
deadlocked the submit gate — the roles that can submit could no longer satisfy it. The
gate is no longer satisfied through a plain save: ``acknowledge_intercompany_movement``
(``facility_asset_movement.py:172``) is a whitelisted POST that checks permlevel-1 write
directly and writes with ``db_set``, and both fields carry ``allow_on_submit`` so the
sign-off is reachable AFTER submit, which is the state a submitted movement is actually in.

This file grades the shipped JSON. The live behaviour of the sign-off — who may give it,
who may not, and that it names the giver — is graded against a site in
``test_accounting_sign_off.py`` beside it.
"""

from __future__ import annotations

import json
import os
import unittest
from pathlib import Path

import apex

_HERE = os.path.join(str(Path(apex.__file__).resolve().parent), "habitat", "doctype", "facility_asset_movement")

ACK_FLAG = "accounting_acknowledged"
ACK_USER = "accounting_acknowledged_by"
ACCOUNTING_ROLE = "Finance Manager"


def load_meta() -> dict:
    with open(os.path.join(_HERE, "facility_asset_movement.json"), encoding="utf-8") as handle:
        return json.load(handle)


def read_controller() -> str:
    with open(os.path.join(_HERE, "facility_asset_movement.py"), encoding="utf-8") as handle:
        return handle.read()


def field(meta: dict, fieldname: str) -> dict:
    return next(f for f in meta["fields"] if f["fieldname"] == fieldname)


def roles_with(meta: dict, ptype: str, permlevel: int = 0) -> set:
    """Roles granted `ptype` at `permlevel`. Document access reads permlevel-0 rows only
    (frappe/permissions.py, is_perm_applicable); field access reads every level."""
    return {
        p["role"] for p in meta["permissions"]
        if int(p.get("permlevel", 0) or 0) == permlevel and p.get(ptype, 0)
    }


class TestTheGateIsReal(unittest.TestCase):
    """The premise, re-proved rather than assumed: this is an enforced gate, so the
    label above it is a claim about who can pass it, not decoration."""

    def test_controller_refuses_an_unacknowledged_permanent_transfer(self):
        source = read_controller()
        self.assertIn('doc.movement_category == "Intercompany Permanent"', source)
        self.assertIn(f"not doc.{ACK_FLAG}", source)

    def test_the_refusal_is_wired_as_a_real_validate_event(self):
        """A gate nothing calls is not a gate. hooks.py must still route validate here."""
        hooks = os.path.join(_HERE, "..", "..", "..", "hooks.py")
        with open(os.path.abspath(hooks), encoding="utf-8") as handle:
            wiring = handle.read()
        self.assertIn(
            "apex.habitat.doctype.facility_asset_movement.facility_asset_movement.validate",
            wiring,
        )


class TestLabelAndPermissionsAgree(unittest.TestCase):

    def setUp(self):
        self.meta = load_meta()

    def test_the_label_no_longer_names_a_role(self):
        """The regression this card exists to prevent: any parenthetical naming an org
        function is a promise the DocPerm rows have to keep."""
        self.assertEqual(field(self.meta, ACK_USER)["label"], "Acknowledged By")

    def test_it_matches_its_two_sibling_user_links_in_the_same_section(self):
        for sibling in ("release_approved_by", "receiving_confirmed_by"):
            self.assertNotIn("(", field(self.meta, sibling)["label"])
            self.assertEqual(field(self.meta, sibling)["options"], "User")
        self.assertEqual(field(self.meta, ACK_USER)["options"], "User")

    def test_finance_manager_holds_the_two_rows_the_gate_needs_and_nothing_more(self):
        """One permlevel-0 read to reach the form, one permlevel-1 read+write to tick the
        flag on it. Any further right is a blanket grant over the whole movement record."""
        rows = {
            int(p.get("permlevel", 0) or 0): p
            for p in self.meta["permissions"]
            if p["role"] == ACCOUNTING_ROLE
        }
        self.assertEqual(set(rows), {0, 1}, "Finance Manager must hold exactly these two rows")
        self.assertTrue(rows[0].get("read"))
        for denied in ("write", "create", "submit", "cancel", "amend", "delete"):
            self.assertFalse(
                rows[0].get(denied),
                f"Finance Manager gained document-level {denied}",
            )
        self.assertTrue(rows[1].get("read"))
        self.assertTrue(rows[1].get("write"))
        for denied in ("create", "submit", "cancel", "amend", "delete"):
            self.assertFalse(rows[1].get(denied), f"the field overlay gained {denied}")

    def test_three_roles_hold_write_not_two(self):
        """The card said two. Resident Supervisor holds permlevel-0 write as well, and
        can therefore edit the movement without being able to submit it."""
        self.assertEqual(
            roles_with(self.meta, "write"),
            {"System Manager", "Accommodation Manager", "Resident Supervisor"},
        )
        self.assertEqual(roles_with(self.meta, "submit"), {"System Manager", "Accommodation Manager"})

    def test_every_writer_of_the_gate_can_also_submit_or_hand_off(self):
        """The gate must stay satisfiable: at least one role can both edit the movement
        and submit it."""
        self.assertTrue(roles_with(self.meta, "write") & roles_with(self.meta, "submit"))


class TestTheAcknowledgementSitsBehindThePermlevel(unittest.TestCase):
    """The narrow grant, held on the schema. Drop the permlevel and any permlevel-0
    writer can close a control they are not entitled to close; drop allow_on_submit and
    nobody can close it at all on the submitted document it belongs to."""

    def setUp(self):
        self.meta = load_meta()

    def test_both_acknowledgement_fields_sit_behind_permlevel_one(self):
        for fieldname in (ACK_FLAG, ACK_USER):
            with self.subTest(field=fieldname):
                self.assertEqual(int(field(self.meta, fieldname).get("permlevel", 0) or 0), 1)

    def test_both_are_reachable_after_submit(self):
        for fieldname in (ACK_FLAG, ACK_USER):
            with self.subTest(field=fieldname):
                self.assertTrue(field(self.meta, fieldname).get("allow_on_submit"))

    def test_the_permlevel_one_grant_reaches_the_two_acknowledgement_fields_only(self):
        """A permlevel is a wall around a named set of fields. Widening that set silently
        hands Finance Manager write on whatever was moved behind it."""
        behind = {
            f["fieldname"] for f in self.meta["fields"]
            if int(f.get("permlevel", 0) or 0) == 1
        }
        self.assertEqual(behind, {ACK_FLAG, ACK_USER})

    def test_accounting_is_the_only_role_that_can_write_behind_the_wall(self):
        self.assertEqual(roles_with(self.meta, "write", permlevel=1), {ACCOUNTING_ROLE})


if __name__ == "__main__":
    unittest.main()
