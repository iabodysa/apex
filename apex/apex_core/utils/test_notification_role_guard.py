# Copyright (c) 2026, AFMCO and contributors
"""Prove ``notification_role_guard`` over the notifications the app ships.

Colocated with the guard, not in ``apex/tests/``: the colocation ratchet
(``tests/test_colocation_ratchet.py``) fails any NEW central test module, and this
one exercises exactly one module. The two disk loaders it needs are the plain-named
shared readers ``apex.tests.shipped_notifications`` and ``apex.tests.shipped_doctypes``
— importable from here because neither is a ``test_*`` module, which is what
``tests/test_no_cross_test_imports.py`` actually bans.

WHAT IS PROVEN, AND WHY EACH PROOF EXISTS
------------------------------------------
1. ``test_detector_reports_a_role_with_no_grant`` — inject a synthetic notification
   naming a role that holds nothing: the detector reports it. On its own this is
   worthless, which is why (2) exists.
2. ``test_detector_stays_silent_for_a_role_that_can_open`` — inject a role that DOES
   hold a permlevel-0 read: the detector does NOT report it. Without this pair, a
   detector that flagged everything unconditionally would pass proof 1.
3. ``test_permlevel_0_clause_is_load_bearing`` — re-derive the predicate with the
   ``permlevel_0`` clause dropped and watch it go blind on a REAL shipped row, not a
   synthetic one: Finance Manager's ``read: 1`` row on Housing Checkout, which sits
   at permlevel 1 and is exactly the shape that fools a detector missing this
   clause. Since the 2026-07-27 grant, no frozen entry is in that state any more, so
   this proof is phrased over the ROW rather than over an entry, as (4) already was.
4. ``test_not_if_owner_clause_is_load_bearing`` — same for ``not_if_owner``. No
   shipped pair is in that state, so this one is proven against the ``All`` /
   ``if_owner`` row Maintenance Request really ships, which is why the assertion is
   phrased over a role rather than over a frozen entry.

Proofs 3 and 4 drop a clause BY NAME through ``roles_that_can_open(clauses=...)``
rather than re-writing a weakened predicate here. A hand-written copy would be a
second implementation, free to drift from the one that ships, and a mutation test
whose mutant is a copy proves nothing about the original.

RESIDUAL GAP, STATED RATHER THAN HIDDEN
----------------------------------------
``unreachable_pairs`` skips a ``document_type`` this app does not ship, so a
notification over an ERPNext or HRMS DocType is never graded — judging another app's
DocPerm table is the line ``report_role_guard._apex_owns`` draws too.
``test_every_notified_document_type_is_ours`` pins that the gap is currently EMPTY,
so the day a notification points at a foreign DocType the exemption becomes visible
instead of silently swallowing the pair.
"""

from __future__ import annotations

import unittest

from apex.apex_core.utils import notification_role_guard as guard
from apex.tests.shipped_doctypes import shipped_doctypes
from apex.tests.shipped_notifications import (
    notification_role_pairs,
    shipped_notifications,
)

# Synthetic identifiers. Prefixed so they can never collide with a shipped name.
_FAKE_DT = "_A301 Notified Record"
_DEAD_ROLE = "_A301 Role Without A Grant"
_LIVE_ROLE = "_A301 Role That Can Open"


# The frozen baseline: exact equality, like the sibling report-role baseline -- a NEW
# offender fails the build, a REPAIRED one fails until pruned. Each entry is
# (document_type, role) -> reason.

# Three of the original seven were drained by REPOINTING: the roles they named --
# Facilities Supervisor, Admin Manager, Operations Director -- hold no DocPerm
# anywhere in this app, so each notification now names a role that already holds a
# permlevel-0 read.

# A FOURTH WAS DRAINED BY GRANT on 2026-07-27, and this paragraph is the reason its
# entry is gone rather than a green build nobody can account for. Custody Damage
# Assessment now ships Finance Manager a permlevel-0, non-if_owner `read`, so the
# receiver of `Habitat - Custody Damage Assessment Created` can open the record the
# mail links to.

# An earlier pass attempted that same grant and reverted it, because the omission was
# recorded as deliberate beside the rows. It was then argued on its own evidence and
# the owner granted it anyway, over three costs he was shown: the shipped role profile
# already pairs the role with Internal Auditor, who holds the read; a level-0 read is
# the WHOLE record, resident identity included, where the permlevel-1 row unlocked one
# field; and Finance Manager is unscoped, so the read spans every building.

# It was the only frozen entry whose notification ships `enabled: 1` -- which is
# precisely why it was the one worth arguing, and why the other three can wait.

# The three survivors ship `enabled: 0`; that is NOT a reason to drop them --
# the DB's `enabled` value overwrites the on-disk one on every re-import
# (frappe/modules/import_file.py:33, consumed :262-265), so a site that toggles one
# on keeps it on, and no migrate will turn it back off.

_CHILD_TABLE_IS_A_DIFFERENT_DEFECT = (
    "Observed, not prescribed — do NOT act on this entry from this file. Rent Payment "
    "Schedule is a child table (istable:1), so NO role can be granted this: "
    "has_permission routes an istable doctype into has_child_permission "
    "(frappe/permissions.py:120-121), which fails closed without a parent_doctype "
    "(:785-790) and a Notification never supplies one. Adding a DocPerm row would not "
    "help and would be misleading. The real question is whether a notification should "
    "name a child table as its document_type at all, or whether it should fire on the "
    "parent and reach the schedule through it — a modelling decision on its own card, "
    "not a permission gap for an agent to close here."
)

KNOWN_UNREACHABLE_NOTIFICATION_ROLES = {
    ("Habitat - Idle Resident Reported", "Idle Resident Report", "HR Manager"): (
        "Observed, not prescribed — do NOT act on this entry from this file. HR Manager "
        "is an HRMS role. It holds a great deal of permission in HRMS and not ONE "
        "DocPerm row anywhere in this app, so it is not a persona apex can grant a "
        "surface to without deciding that apex now owns an HRMS role's access. Idle "
        "Resident Report carries resident identity and idleness findings; whether the "
        "HR function should read that across every building is a personnel-data "
        "decision for the owner, not a technical gap. The alternative — repointing at "
        "an apex role that can already open it, as A-301 did for the three "
        "dead-role entries — is a change of AUDIENCE, and this notification's audience "
        "being HR is the point of it."
    ),
    ("Habitat - Rent Payment Due", "Rent Payment Schedule", "Accommodation Manager"): (
        _CHILD_TABLE_IS_A_DIFFERENT_DEFECT
    ),
    ("Habitat - Rent Payment Due", "Rent Payment Schedule", "Finance Manager"): (
        _CHILD_TABLE_IS_A_DIFFERENT_DEFECT
    ),
}


class TestShippedNotificationReceiversCanOpenTheRecord(unittest.TestCase):
    """The ratchet: exactly the frozen pairs offend, no more and no fewer."""

    @classmethod
    def setUpClass(cls):
        cls.doctypes = shipped_doctypes()
        cls.pairs = notification_role_pairs()

    def test_scan_reaches_the_shipped_notifications(self):
        """A parser that found nothing would pass every assertion below."""
        names = {name for name, _dt, _role, _en in self.pairs}
        self.assertIn(
            "Habitat - Severe Safety Incident",
            names,
            "Notification scan found nothing — the loader broke, and a broken loader "
            "makes every other test in this module vacuously green",
        )
        self.assertGreater(len(self.pairs), 30, "implausibly few notification/role pairs")

    def test_only_the_frozen_pairs_are_unreachable(self):
        found = guard.unreachable_pairs(self.pairs, self.doctypes)
        expected = sorted(KNOWN_UNREACHABLE_NOTIFICATION_ROLES)
        self.assertEqual(
            found,
            expected,
            "shipped notification receiver reachability changed. A NEW entry means that "
            "role is EMAILED about a record it cannot open — the resolver passes "
            "ignore_permissions=True (notification.py:366), so delivery succeeds and the "
            "link in the message throws PermissionError on click, with no signal "
            "anywhere. Either grant that role a permlevel-0 non-if_owner read on the "
            "document_type, or repoint receiver_by_role at a role that already holds "
            "one (and bump the notification's `modified`, or migrate skips the "
            "re-import: import_file.py:143-144). A MISSING entry means one was repaired "
            "and this baseline must shrink to match.",
        )

    def test_every_frozen_entry_carries_a_reason(self):
        for key, why in KNOWN_UNREACHABLE_NOTIFICATION_ROLES.items():
            with self.subTest(pair=key):
                self.assertTrue(why and why.strip(), f"{key} is frozen with no reason")

    def test_no_frozen_entry_names_something_the_app_stopped_shipping(self):
        """A drained notification or a renamed role must not leave a stale entry.

        Without this, deleting a notification would silently satisfy its frozen entry
        forever and the exact-equality check above would start passing for the wrong
        reason.
        """
        live = {(name, dt, role) for name, dt, role, _en in self.pairs}
        phantom = sorted(set(KNOWN_UNREACHABLE_NOTIFICATION_ROLES) - live)
        self.assertEqual(
            phantom,
            [],
            "the baseline names notification/role pair(s) the app no longer ships",
        )

    def test_every_notified_document_type_is_ours(self):
        """Pin the one exemption in ``unreachable_pairs`` to the empty set.

        A ``document_type`` this app does not ship is skipped rather than graded. That
        is deliberate, but it is also a hole: if it ever stops being empty, the pair it
        swallows must become visible here rather than in a silent pass.
        """
        foreign = sorted(
            {dt for _n, dt, _r, _en in self.pairs if dt not in self.doctypes}
        )
        self.assertEqual(
            foreign,
            [],
            "notification(s) point at a DocType this app does not ship, so the guard "
            "does not grade them — decide whether to grade another app's DocPerms",
        )

    def test_repointed_notifications_carry_a_bumped_modified(self):
        """The three repointed notifications must actually reach a site.

        A shipped Notification whose on-disk ``modified`` is not strictly newer than the
        row already in the DB is skipped by ``import_file_by_path``
        (frappe/modules/import_file.py:143-144; note the ``<=`` on :127). The
        ``migration_hash`` content compare that rescues a DocType is gated on
        ``doctype == "DocType"`` (:132) and does not apply here. This asserts the
        stamps were bumped past the values they carried before the repoint, so it
        cannot be shipped as a silent no-op.
        """
        previous = {
            "Habitat - Maintenance From Safety - Facilities Supervisor": "2026-06-23 12:00:00.000000",
            "Habitat - Severe Safety Incident": "2026-07-10 06:05:34.129545",
        }
        stamps = {
            data.get("name"): data.get("modified")
            for _path, data in shipped_notifications()
            if data.get("name") in previous
        }
        self.assertEqual(sorted(stamps), sorted(previous), "a repointed notification vanished")
        for name, was in previous.items():
            with self.subTest(notification=name):
                self.assertGreater(
                    stamps[name],
                    was,
                    f"{name} was repointed but its `modified` is not newer than {was} — "
                    "migrate will skip the re-import and the old receiver keeps the row",
                )


class TestTheDetectorReportsAndStaysSilent(unittest.TestCase):
    """Proofs 1 and 2 — the detector must fire, and must NOT fire, on demand."""

    DOCTYPES = {
        _FAKE_DT: {
            "name": _FAKE_DT,
            "permissions": [{"role": _LIVE_ROLE, "read": 1}],
        }
    }

    def test_detector_reports_a_role_with_no_grant(self):
        pairs = [("_A301 Alert", _FAKE_DT, _DEAD_ROLE, True)]
        self.assertEqual(
            guard.unreachable_pairs(pairs, self.DOCTYPES),
            [("_A301 Alert", _FAKE_DT, _DEAD_ROLE)],
        )

    def test_detector_stays_silent_for_a_role_that_can_open(self):
        """Proof 1 alone is satisfied by a detector that flags everything."""
        pairs = [("_A301 Alert", _FAKE_DT, _LIVE_ROLE, True)]
        self.assertEqual(guard.unreachable_pairs(pairs, self.DOCTYPES), [])

    def test_a_child_table_denies_the_role_that_would_otherwise_pass(self):
        """istable short-circuits before the permission table is even read."""
        doctypes = {_FAKE_DT: dict(self.DOCTYPES[_FAKE_DT], istable=1)}
        pairs = [("_A301 Alert", _FAKE_DT, _LIVE_ROLE, True)]
        self.assertEqual(
            guard.unreachable_pairs(pairs, doctypes),
            [("_A301 Alert", _FAKE_DT, _LIVE_ROLE)],
        )

    def test_administrator_is_never_the_offender(self):
        pairs = [("_A301 Alert", _FAKE_DT, "Administrator", True)]
        self.assertEqual(guard.unreachable_pairs(pairs, self.DOCTYPES), [])


class TestEachClauseIsLoadBearing(unittest.TestCase):
    """Proofs 3 and 4 — drop one clause, watch the predicate go blind on a REAL row.

    Both mutants are re-derived from the shipping clause bodies via
    ``clauses=...``; neither is a re-implementation, so a drift between the mutant
    and the original is impossible by construction.
    """

    @classmethod
    def setUpClass(cls):
        cls.doctypes = shipped_doctypes()

    def _perms(self, name):
        data = self.doctypes[name]
        return data.get("permissions"), data.get("istable")

    def test_permlevel_0_clause_is_load_bearing(self):
        """Housing Checkout really ships Finance Manager at permlevel 1 ONLY.

        The anchor moved here on 2026-07-27. Custody Damage Assessment used to carry
        both this shape and a frozen entry, so the proof could be phrased over the
        entry; it was then granted a permlevel-0 read and stopped being an example of
        the shape at all. No shipped notification names this pair, so the assertion is
        phrased over the ROW, exactly as the ``not_if_owner`` proof below already is.
        The row is real, carries ``read: 1``, and is precisely what a detector missing
        the permlevel clause would misread as a grant.
        """
        permissions, istable = self._perms("Housing Checkout")

        rows = [r for r in permissions if r.get("role") == "Finance Manager"]
        self.assertEqual(
            sorted(int(r.get("permlevel") or 0) for r in rows),
            [1],
            "this proof needs Finance Manager at permlevel 1 ONLY on Housing "
            "Checkout; the fixture it is built on changed",
        )
        self.assertTrue(rows[0].get("read"), "the row must carry read for the mutant to bite")

        self.assertNotIn(
            "Finance Manager",
            guard.roles_that_can_open(permissions, istable),
            "with the clause present, a permlevel-1-only role cannot open the record",
        )
        self.assertIn(
            "Finance Manager",
            guard.roles_that_can_open(
                permissions, istable, clauses=("read", "not_if_owner")
            ),
            "MUTANT SURVIVED: with the permlevel_0 clause dropped, the detector still "
            "refused a permlevel-1-only role, so the clause is not what catches it",
        )

    def test_not_if_owner_clause_is_load_bearing(self):
        """Maintenance Request really ships an ``All`` + ``if_owner`` read row.

        No shipped notification names ``All``, so this cannot be proven through a frozen
        entry — but the ROW is real, and it is the exact shape that reads as ``read: 1``
        at DocType level (frappe/permissions.py:307) while every document is filtered
        away per row (db_query.py:1440). A receiver in that state opens a list, sees
        nothing, and is shown no error at all.
        """
        permissions, istable = self._perms("Maintenance Request")

        owner_scoped = [
            r
            for r in permissions
            if r.get("if_owner") and r.get("read") and not int(r.get("permlevel") or 0)
        ]
        self.assertTrue(
            owner_scoped,
            "this proof needs a real if_owner read row on Maintenance Request; the "
            "fixture it is built on changed",
        )
        role = owner_scoped[0]["role"]

        self.assertNotIn(
            role,
            guard.roles_that_can_open(permissions, istable),
            f"with the clause present, the if_owner-only role {role!r} cannot be "
            "treated as able to open an arbitrary document",
        )
        self.assertIn(
            role,
            guard.roles_that_can_open(permissions, istable, clauses=("read", "permlevel_0")),
            "MUTANT SURVIVED: with the not_if_owner clause dropped, the detector still "
            f"refused {role!r}, so the clause is not what catches an owner-scoped grant",
        )


if __name__ == "__main__":
    unittest.main()
