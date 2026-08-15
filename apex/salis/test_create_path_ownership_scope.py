# Copyright (c) 2026, AFMCO and contributors
"""A-233 — ownership is not an access basis on an UNSAVED row.

``Document.insert`` stamps ``owner`` with the acting user (frappe/model/document.py:298)
two statements before ``check_permission("create")`` (:300). The creator is therefore
ALWAYS the owner at the create check, so the five rules that tested ownership first
returned None — defer — for every create and never reached their scope test. A scoped
user could create a record under another scope's parent: a Trip Start Log on another
project's Dispatch Trip, a Driver Attendance or Driver Suspension on another project's
driver, a Boarding Scan Log on another project's trip. (Salis Driver was masked by
Frappe's native User Permission match on its direct ``project`` Link; the other four
carry no link a Project User Permission matches, so nothing caught them.)

THE RULE THESE TESTS PIN: ownership is an access basis only for a row that already
exists. On an unsaved row ``owner == user`` states who is asking, not anything about the
row, so the row must anchor itself — its project must be in scope, or its driver link
(or its parent trip's driver) must be the acting user's own Salis Driver. Once stored,
ownership is a durable fact and is sufficient again. The rules stay deny-only and
ptype-agnostic: the discriminator is ``__islocal``, the document's storage state, never
``ptype``. ``test_no_ptype_changes_any_verdict`` holds that contract.

THE ENTRY POINT IS ONE FUNCTION. ``hooks.py`` registers
``project_scoped_has_permission`` for every scoped Salis DocType; it reads
``doc.doctype``, looks the DocType up in ``SALIS_SCOPE`` and calls that DocType's rule
from ``DOCUMENT_RULES``. The five DocTypes below reach two rules that way — Trip Start
Log and Salis Driver land on ``_owner_or_project_has_permission``, the three
driver-linked ones on ``_driver_chain_has_permission`` with ``with_owner=True`` — so
every verdict here is taken through the same call the framework makes.

EVERY VERDICT BELOW IS TAKEN WITH THE CREATOR AS OWNER, so ownership cannot mask the
result, and the allow and the refuse are asserted as a PAIR — a rule that let every
create through would pass the allow half alone, and one that blocked every create would
pass the refuse half alone. ``test_the_two_verdicts_are_never_the_same_verdict`` fails on
either collapse.

WHY THESE TESTS ARE SITELESS. The bench is shared, so nothing here touches a site: the
module-level scope resolvers and the driver resolver are stubbed (the documented stub
points) and ``frappe.db.get_value`` is a constructed lookup over the tables below.

A RUNTIME LOGIN DEMONSTRATION IS THEREFORE STILL OWED and is NOT provided here: log in
as a Fleet Supervisor holding a User Permission for one project, create a Driver
Attendance against a driver in that project and confirm it saves, then repeat against
another project's driver and confirm it raises PermissionError — and confirm a Driver
still records their own attendance from the desk while holding no Project User
Permission.
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

import frappe

from apex.salis import permissions as SP

PROJ_A = "PROJ-A"
PROJ_B = "PROJ-B"

CREATOR = "supervisor@example.com"

DRIVERS = {"DRV-A": PROJ_A, "DRV-B": PROJ_B}
ROUTE_PLANS = {"RP-A": PROJ_A, "RP-B": PROJ_B}
TRIPS = {
    "TRIP-A": {"project": None, "route_plan": "RP-A", "driver": "DRV-A"},
    "TRIP-B": {"project": None, "route_plan": "RP-B", "driver": "DRV-B"},
}

_ABSENT = object()


def _doc(doctype, unsaved, **fields):
    """A constructed document, optionally carrying the framework's unsaved flag.

    ``owner`` defaults to the acting user because that is what ``insert`` guarantees at
    the create check — these proofs are worthless if the creator is not the owner.
    ``__islocal`` is set through ``setattr`` with a string so no name mangling applies;
    it is exactly the attribute ``Document.insert`` sets at document.py:295.
    """
    fields.setdefault("owner", CREATOR)
    doc = SimpleNamespace(doctype=doctype, **fields)
    if unsaved:
        setattr(doc, "__islocal", True)
    return doc


# Each DocType with the parent link that anchors it at the create check, in-scope and
# out-of-scope. Trip Start Log and Boarding Scan Log leave their fetched `driver` (and
# Trip Start Log its fetched `route_plan`) empty, as `insert` does at :300.
CREATE_CASES = [
    (
        "Trip Start Log",
        {"dispatch_trip": "TRIP-A", "route_plan": None, "driver": None},
        {"dispatch_trip": "TRIP-B", "route_plan": None, "driver": None},
        {"dispatch_trip": None, "route_plan": None, "driver": None},
    ),
    (
        "Salis Driver",
        {"project": PROJ_A},
        {"project": PROJ_B},
        {"project": None},
    ),
    (
        "Driver Attendance",
        {"driver": "DRV-A"},
        {"driver": "DRV-B"},
        {"driver": None},
    ),
    (
        "Driver Suspension",
        {"driver": "DRV-A"},
        {"driver": "DRV-B"},
        {"driver": None},
    ),
    (
        "Boarding Scan Log",
        {"dispatch_trip": "TRIP-A", "driver": None},
        {"dispatch_trip": "TRIP-B", "driver": None},
        {"dispatch_trip": None, "driver": None},
    ),
]

# The subset a Driver may create for themselves, with the link that carries their own
# driver at the create check. Salis Driver is absent on purpose: the Driver role holds no
# create DocPerm on it, so it has no self-service create path to protect.
DRIVER_SELF_CASES = [
    ("Trip Start Log", "dispatch_trip", "TRIP-A", "TRIP-B"),
    ("Driver Attendance", "driver", "DRV-A", "DRV-B"),
    ("Driver Suspension", "driver", "DRV-A", "DRV-B"),
    ("Boarding Scan Log", "dispatch_trip", "TRIP-A", "TRIP-B"),
]


class _ScopeCase(unittest.TestCase):
    """A constructed session, db and scope, and no site anywhere."""

    def setUp(self):
        self._stub_local("session", frappe._dict(user=CREATOR))
        self._stub_local("db", SimpleNamespace(get_value=self._get_value))
        self.own_driver(None)

    @staticmethod
    def verdict(doc, ptype, user=None):
        """The framework's own entry point, so the dispatch is under test too."""
        return SP.project_scoped_has_permission(doc, ptype, user=user)

    def _stub_local(self, name, value):
        """Install a stub on ``frappe.local``, queueing its restore BEFORE the write.

        `frappe.db` / `frappe.session` are proxies onto `frappe.local`, so a stub left
        installed is inherited by every later test in the run; registering the cleanup
        after the mutation would strand it if anything in between throws.
        """
        self.addCleanup(self._restore_local, name, getattr(frappe.local, name, _ABSENT))
        setattr(frappe.local, name, value)

    @staticmethod
    def _restore_local(name, original):
        """Absence is a value: werkzeug's ``Local`` raises for an unset name, so leaving
        ``None`` behind is not the same as never having stubbed."""
        if original is _ABSENT:
            try:
                delattr(frappe.local, name)
            except AttributeError:
                pass
        else:
            setattr(frappe.local, name, original)

    @staticmethod
    def _get_value(doctype, name, fieldname, as_dict=False):
        """Both read shapes ``permissions`` uses.

        ``_dispatch_trip_project`` reads ``project`` and ``route_plan`` off a Dispatch
        Trip in ONE call, as a list of fields with ``as_dict=True``; everything else
        reads a single column. A stub serving only the single-column shape would raise
        on the trip read rather than answer it.
        """
        if isinstance(fieldname, (list, tuple)):
            row = TRIPS.get(name) if doctype == "Dispatch Trip" else None
            if not row:
                return None
            values = {field: row.get(field) for field in fieldname}
            return frappe._dict(values) if as_dict else [values[f] for f in fieldname]
        if doctype == "Salis Driver" and fieldname == "project":
            return DRIVERS.get(name)
        if doctype == "Route Plan" and fieldname == "project":
            return ROUTE_PLANS.get(name)
        if doctype == "Dispatch Trip":
            return TRIPS.get(name, {}).get(fieldname)
        return None

    def _patch(self, attr, value):
        patcher = patch.object(SP, attr, return_value=value)
        patcher.start()
        self.addCleanup(patcher.stop)

    def scoped(self, projects=(PROJ_A,)):
        self._patch("_is_unscoped", False)
        self._patch("_allowed_projects", list(projects))
        self._stub_user_permissions(projects)

    def unscoped(self):
        self._patch("_is_unscoped", True)
        self._stub_user_permissions(())

    def _stub_user_permissions(self, projects):
        """Serve the ``applicable_for`` narrowing without a database.

        ``permission_scope.for_doctype`` re-reads frappe's own User Permission rows
        (permission_scope.py:104) to drop any value whose rows ALL name a different
        doctype. That read is real and is the point of the narrowing, so it is
        answered here with rows matching the scope this test already granted, each
        carrying no ``applicable_for`` — the row shape a plain project grant produces.
        Values pass the filter and the assertions below still grade ownership rather
        than the narrowing.
        """
        rows = {"Project": [{"doc": p, "applicable_for": None} for p in projects]}
        patcher = patch.object(
            frappe.permissions, "get_user_permissions", return_value=rows
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def own_driver(self, driver):
        """Point the User -> Employee -> Salis Driver chain at ``driver`` (or nothing)."""
        self._patch("get_driver_for_session_user", driver)


class TestAnUnsavedRowIsDecidedByItsParentNotItsOwner(_ScopeCase):
    """Proof 1 — the two verdicts, creator as owner in both."""

    def test_an_in_scope_parent_allows_the_create(self):
        self.scoped()
        for label, in_scope, _out, _none in CREATE_CASES:
            with self.subTest(doctype=label):
                doc = _doc(label, True, **in_scope)
                self.assertEqual(doc.owner, CREATOR)
                self.assertIsNone(
                    self.verdict(doc, "create"),
                    f"{label}: a scoped user cannot create inside their own project",
                )

    def test_an_out_of_scope_parent_refuses_the_create(self):
        """The leak A-233 names: the creator owns the row, so ownership must not decide."""
        self.scoped()
        for label, _in, out_of_scope, _none in CREATE_CASES:
            with self.subTest(doctype=label):
                doc = _doc(label, True, **out_of_scope)
                self.assertEqual(doc.owner, CREATOR)
                self.assertIs(
                    self.verdict(doc, "create"),
                    False,
                    f"{label}: a scoped user created under another scope's parent",
                )

    def test_the_two_verdicts_are_never_the_same_verdict(self):
        """Fails on either collapse — allow-everything AND block-everything."""
        self.scoped()
        for label, in_scope, out_of_scope, _none in CREATE_CASES:
            with self.subTest(doctype=label):
                verdicts = (
                    self.verdict(_doc(label, True, **in_scope), "create"),
                    self.verdict(_doc(label, True, **out_of_scope), "create"),
                )
                self.assertEqual(verdicts, (None, False), f"{label}: verdicts collapsed")

    def test_an_unanchored_create_fails_closed(self):
        """No parent link at all: ownership is the only thing left, and it is not enough."""
        self.scoped()
        for label, _in, _out, unanchored in CREATE_CASES:
            with self.subTest(doctype=label):
                self.assertIs(self.verdict(_doc(label, True, **unanchored), "create"), False)

    def test_a_scoped_user_holding_no_project_is_refused_too(self):
        self.scoped(projects=())
        for label, in_scope, _out, _none in CREATE_CASES:
            with self.subTest(doctype=label):
                self.assertIs(self.verdict(_doc(label, True, **in_scope), "create"), False)

    def test_oversight_still_defers(self):
        self.unscoped()
        for label, _in, out_of_scope, _none in CREATE_CASES:
            with self.subTest(doctype=label):
                self.assertIsNone(self.verdict(_doc(label, True, **out_of_scope), "create"))


class TestOwnershipStillDecidesAStoredRow(_ScopeCase):
    """Proof 2 — the if_owner basis survives everywhere it was already valid.

    Same documents, same out-of-scope parent, same owner — only the unsaved flag differs.
    If this class and Proof 1 both pass, the change is confined to the create check.
    """

    def test_the_owner_may_still_act_on_their_own_out_of_scope_row(self):
        self.scoped()
        for label, _in, out_of_scope, _none in CREATE_CASES:
            with self.subTest(doctype=label):
                self.assertIsNone(
                    self.verdict(_doc(label, False, **out_of_scope), "read"),
                    f"{label}: the if_owner self-access basis was lost",
                )

    def test_a_non_owner_is_still_denied_an_out_of_scope_row(self):
        self.scoped()
        for label, _in, out_of_scope, _none in CREATE_CASES:
            with self.subTest(doctype=label):
                doc = _doc(label, False, owner="stranger@example.com", **out_of_scope)
                self.assertIs(self.verdict(doc, "read"), False)

    def test_a_non_owner_is_still_allowed_an_in_scope_row(self):
        self.scoped()
        for label, in_scope, _out, _none in CREATE_CASES:
            with self.subTest(doctype=label):
                doc = _doc(label, False, owner="stranger@example.com", **in_scope)
                self.assertIsNone(self.verdict(doc, "read"))

    def test_a_doc_carrying_no_flag_is_treated_as_stored(self):
        """The flag is the whole discriminator, so pin what its absence means.

        ``Document.insert`` deletes ``__islocal`` once the row is written
        (document.py:338), so a doc read back from the database never carries it.
        """
        self.scoped()
        doc = _doc("Driver Attendance", False, driver="DRV-B")
        self.assertFalse(hasattr(doc, "__islocal"))
        self.assertFalse(SP._is_unsaved(doc))
        self.assertIsNone(self.verdict(doc, "create"))


class TestTheDriverSelfServiceCreateIsNotCollateral(_ScopeCase):
    """Proof 3 — a blackout would be worse than the leak, so prove the create still works.

    A Driver holds NO Project User Permission, so once ownership stopped rescuing an
    unsaved row the project test alone would deny every self-service create. The durable
    driver-own basis carries it instead — and must not carry another driver's row.
    """

    def test_a_driver_may_create_their_own_row(self):
        self.scoped(projects=())
        self.own_driver("DRV-A")
        for label, field, mine, _theirs in DRIVER_SELF_CASES:
            with self.subTest(doctype=label):
                self.assertIsNone(
                    self.verdict(_doc(label, True, **{field: mine}), "create"),
                    f"{label}: a Driver can no longer create their own row",
                )

    def test_a_driver_may_not_create_on_another_drivers_parent(self):
        self.scoped(projects=())
        self.own_driver("DRV-A")
        for label, field, _mine, theirs in DRIVER_SELF_CASES:
            with self.subTest(doctype=label):
                self.assertIs(
                    self.verdict(_doc(label, True, **{field: theirs}), "create"),
                    False,
                    f"{label}: the driver-own basis laundered another driver's row",
                )

    def test_the_driver_basis_needs_a_resolved_driver(self):
        """A user with no Salis Driver gets nothing from the fallback."""
        self.scoped(projects=())
        self.own_driver(None)
        for label, field, mine, _theirs in DRIVER_SELF_CASES:
            with self.subTest(doctype=label):
                self.assertIs(
                    self.verdict(_doc(label, True, **{field: mine}), "create"), False
                )


class TestTheHandlersStayPtypeAgnostic(_ScopeCase):
    """Proof 4 — the contract the obvious fix would have broken.

    These rules are deny-only and ptype-agnostic by contract: the same denial applies
    to every action. Branching on ``ptype`` was the tempting fix and would have broken
    that; branching on the document's storage state does not.
    """

    PTYPES = ("create", "read", "write", "submit", "cancel", "delete")

    def test_no_ptype_changes_any_verdict(self):
        self.scoped()
        for label, in_scope, out_of_scope, _none in CREATE_CASES:
            for ptype in self.PTYPES:
                with self.subTest(doctype=label, ptype=ptype):
                    self.assertIsNone(self.verdict(_doc(label, True, **in_scope), ptype))
                    self.assertIs(
                        self.verdict(_doc(label, True, **out_of_scope), ptype), False
                    )

    def test_every_verdict_is_deny_only(self):
        """A rule may return False (block) or None (defer) — never a grant."""
        self.scoped()
        for label, in_scope, out_of_scope, unanchored in CREATE_CASES:
            for fields in (in_scope, out_of_scope, unanchored):
                for unsaved in (True, False):
                    with self.subTest(doctype=label, unsaved=unsaved, fields=fields):
                        verdict = self.verdict(_doc(label, unsaved, **fields), "create")
                        self.assertIn(verdict, (None, False))


class TestTheGuardIsLoadBearing(_ScopeCase):
    """Proof 5 — neutralise the discriminator and the leak must come back.

    A regression test that cannot fail is worthless. Forcing ``_is_unsaved`` to False
    reproduces the pre-A-233 rules exactly — ownership tested first, unconditionally —
    so every out-of-scope create must be admitted again. If this class ever passes while
    ``TestAnUnsavedRowIsDecidedByItsParentNotItsOwner`` also passes, the fix is real; if
    this one starts failing, the proofs above have stopped proving anything.
    """

    def test_neutralising_the_unsaved_check_reopens_the_leak(self):
        self.scoped()
        with patch.object(SP, "_is_unsaved", return_value=False):
            for label, _in, out_of_scope, _none in CREATE_CASES:
                with self.subTest(doctype=label):
                    self.assertIsNone(
                        self.verdict(_doc(label, True, **out_of_scope), "create"),
                        f"{label}: the pre-fix leak no longer reproduces, so the create "
                        "proofs above are not testing what they claim",
                    )


if __name__ == "__main__":
    unittest.main(verbosity=2)
