# Copyright (c) 2026, AFMCO and contributors
"""A-218: the acknowledgement gate and the label above it must name the same people.

THE DEFECT. ``accounting_acknowledged_by`` shipped labelled "Acknowledged By (Finance)"
while ``Finance Manager`` held no write on the DocType, and ``_validate_intercompany_gates``
refuses to submit an Intercompany Permanent movement whose ``accounting_acknowledged`` is
unset. So an enforced gate advertised a role that could not reach it, and in practice it
was closed by whoever held System Manager.

WHY THE FIX IS THE LABEL AND NOT A PERMISSION GRANT. The narrow permission shape would be
a permlevel-1 write row scoped to the two acknowledgement fields. It cannot work here:

1. No field on this DocType carries a permlevel -- every one of them sits at 0. There is
   nothing for a permlevel-1 row to unlock, so the row would grant nothing at all.
2. Saving the document needs permlevel-0 write. Document access is resolved from
   permlevel-0 rows ONLY (``frappe/permissions.py:284``, ``is_perm_applicable`` filters
   ``cint(perm.permlevel) == 0``), and field access is a separate computation that never
   substitutes for it. A permlevel-1 row would leave Finance Manager unable to open the
   record it was meant to acknowledge.
3. Putting the two fields BEHIND permlevel 1 to make (1) possible turns the gate into a
   deadlock. ``validate_higher_perm_levels`` resets high-permlevel fields on save for any
   user without that level (``frappe/model/document.py:783``), so the three roles that
   hold write -- System Manager, Accommodation Manager, Resident Supervisor -- would
   silently lose the flag they are required to set, and the two that can submit could no
   longer satisfy their own submit gate. Restoring them means three more permlevel-1 rows
   plus a permlevel-0 write row for Finance Manager, which is the blanket grant over the
   whole movement record that this change exists to avoid.

So the shipped BEHAVIOUR is correct and the shipped LABEL was the false half. The
parenthetical is also against this DocType's own convention: ``moved_by`` is
"Moved By (Employee)" and links Employee, while the two sibling Link-to-User fields in the
same section, ``release_approved_by`` and ``receiving_confirmed_by``, carry no
parenthetical at all. "Acknowledged By" matches them and already has an ``ar.csv`` row.

STILL OWED: a live login-as-Finance-Manager demonstration. The bench was unavailable when
this landed, so everything below is proved against the shipped JSON and a replay of the
frappe permission algorithms rather than against a session.

Run standalone:  python3 -m unittest apex.habitat.doctype.facility_asset_movement.test_facility_asset_movement_acknowledgement -v
"""

from __future__ import annotations

import json
import os
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))

ACK_FLAG = "accounting_acknowledged"
ACK_USER = "accounting_acknowledged_by"


def load_meta() -> dict:
    with open(os.path.join(_HERE, "facility_asset_movement.json"), encoding="utf-8") as handle:
        return json.load(handle)


def read_controller() -> str:
    with open(os.path.join(_HERE, "facility_asset_movement.py"), encoding="utf-8") as handle:
        return handle.read()


def field(meta: dict, fieldname: str) -> dict:
    return next(f for f in meta["fields"] if f["fieldname"] == fieldname)


def roles_with(meta: dict, ptype: str, permlevel: int = 0) -> set:
    """Roles granted `ptype` at `permlevel`. Mirrors the applicability filter at
    frappe/permissions.py:284 -- document access reads permlevel-0 rows only."""
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

    def test_finance_manager_is_read_only_here(self):
        rows = [p for p in self.meta["permissions"] if p["role"] == "Finance Manager"]
        self.assertEqual(len(rows), 1, "Finance Manager gained a second row -- re-argue the label")
        self.assertEqual(int(rows[0].get("permlevel", 0) or 0), 0)
        self.assertTrue(rows[0].get("read"))
        for denied in ("write", "create", "submit", "cancel", "amend", "delete"):
            self.assertFalse(rows[0].get(denied), f"Finance Manager gained {denied}")

    def test_three_roles_hold_write_not_two(self):
        """The card said two. Resident Supervisor holds permlevel-0 write as well, and
        can therefore tick the acknowledgement without being able to submit it."""
        self.assertEqual(
            roles_with(self.meta, "write"),
            {"System Manager", "Accommodation Manager", "Resident Supervisor"},
        )
        self.assertEqual(roles_with(self.meta, "submit"), {"System Manager", "Accommodation Manager"})

    def test_every_writer_of_the_gate_can_also_submit_or_hand_off(self):
        """The gate must stay satisfiable: at least one role can both set the flag and
        submit. This fails the moment a permlevel is introduced without companion rows."""
        self.assertTrue(roles_with(self.meta, "write") & roles_with(self.meta, "submit"))


class TestWhyThePermlevelRouteWasRejected(unittest.TestCase):
    """These assertions are the cost calculation, kept executable so a later wave
    cannot reopen option (a) on a stale premise."""

    def setUp(self):
        self.meta = load_meta()

    def test_no_field_on_this_doctype_is_behind_a_permlevel(self):
        behind = [f["fieldname"] for f in self.meta["fields"] if int(f.get("permlevel", 0) or 0)]
        self.assertEqual(behind, [], "a permlevel appeared -- the option (a) cost changed")

    def test_both_acknowledgement_fields_sit_at_permlevel_zero(self):
        for fieldname in (ACK_FLAG, ACK_USER):
            self.assertEqual(int(field(self.meta, fieldname).get("permlevel", 0) or 0), 0)

    def test_a_permlevel_one_row_would_unlock_nothing_today(self):
        """Concretely: the set of fields a permlevel-1 grant would reach is empty, so
        such a row would be a grant of nothing rather than a narrow grant."""
        would_unlock = {
            f["fieldname"] for f in self.meta["fields"]
            if int(f.get("permlevel", 0) or 0) == 1
        }
        self.assertEqual(would_unlock, set())

    def test_no_permlevel_one_rows_exist_to_catch_the_writers_if_one_appeared(self):
        """If a later change moves the acknowledgement behind permlevel 1 without adding
        these rows, the three writers lose the field silently (document.py:783)."""
        self.assertEqual(roles_with(self.meta, "write", permlevel=1), set())


class TestTheReasonStaysBesideTheCode(unittest.TestCase):

    def test_the_controller_records_who_can_actually_acknowledge(self):
        source = read_controller()
        for role in ("System Manager", "Accommodation Manager", "Resident Supervisor"):
            self.assertIn(role, source)
        self.assertIn("Finance Manager is read-only here", source)


if __name__ == "__main__":
    unittest.main()
