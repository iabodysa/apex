# Copyright (c) 2026, AFMCO and contributors
"""A-250 — a project-less create is decided per DocType, never by a blanket rule.

``scoped_has_permission`` treats OWNERSHIP as the escape for a doc that anchors to no
project. ``Document.insert`` stamps ``owner`` with the acting user
(frappe/model/document.py:298) two statements before ``check_permission("create")``
(:300), so at the create check ``owner == user`` is a tautology and that escape admitted
EVERY project-less create — the same shape A-233 closed in the owner-basis handlers,
here on the handler wired to eleven DocTypes.

WHY THE FIX IS A NAMED SET AND NOT THE RULE. A blanket application of A-233's unsaved
discriminator would deny a project-less create on all eleven, and on ten of them that
create is a modelled business state, not a leak — the survey behind
``PROJECT_MANDATORY_ON_CREATE`` is in its docstring. Only where the DocType's own model
marks ``project`` ``reqd`` is a project-less row impossible by construction, and there
the desk cannot even produce one (``frappe.ui.form.check_mandatory`` gates the save call,
save.js:20), so nothing a human reaches is denied — only a programmatic insert that skips
the mandatory check.

WHAT THESE TESTS PIN, in three halves that must all hold together:
  1. On the tightened DocType the two verdicts separate — an in-scope create allowed, an
     out-of-scope create refused, and a project-less create refused — WITH THE CREATOR AS
     OWNER IN EVERY CASE, so ownership cannot be what produced the result. Each pair is
     asserted as a pair: a handler that allowed everything would pass the allow half
     alone, one that blocked everything would pass the refuse half alone.
  2. On the other ten the project-less create still passes. A fix whose blast radius
     exceeded the harm is the reason A-250 was left open, so the non-blackout is a
     first-class assertion, not an afterthought.
  3. The set is not free-floating: every member must really carry ``reqd`` on ``project``
     in its own DocType JSON, and the wiring read out of ``hooks.py`` must still be the
     eleven DocTypes this survey covered.

WHY THESE TESTS ARE SITELESS. The bench is shared, so nothing here touches a site: the
scope resolvers are stubbed at the documented stub points and ``frappe.db.get_value`` is
a constructed lookup over the tables below. The DocType JSON and ``hooks.py`` are read
from the source tree, not from a database.

A RUNTIME LOGIN DEMONSTRATION IS THEREFORE STILL OWED: log in as a Fleet Supervisor
holding a User Permission for one project, confirm a Fuel Claim still saves for that
project, and confirm an ordinary project-less Transport Request / Route Plan / Issue
still saves — that is the half a constructed proof cannot show.
"""

from __future__ import annotations

import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import frappe

from apex.salis import permissions as SP

PROJ_A = "PROJ-A"
PROJ_B = "PROJ-B"

CREATOR = "supervisor@example.com"
STRANGER = "someone.else@example.com"

ROUTE_PLANS = {"RP-A": PROJ_A, "RP-B": PROJ_B}
TRIPS = {"TRIP-A": {"route_plan": "RP-A"}, "TRIP-B": {"route_plan": "RP-B"}}

_ABSENT = object()


def _stored(doctype, **fields):
    """A constructed document as read back from the database — no unsaved flag.

    ``Document.insert`` deletes ``__islocal`` once the row is written (document.py:338),
    so its absence IS the statement that the row exists. ``owner`` defaults to the acting
    user because that is what ``insert`` guarantees at the create check; these proofs are
    worthless if the creator is not the owner.
    """
    fields.setdefault("owner", CREATOR)
    return SimpleNamespace(doctype=doctype, **fields)


def _unsaved(doctype, **fields):
    """The same document as ``insert`` holds it at ``check_permission("create")``.

    ``__islocal`` is set through ``setattr`` with a string so no name mangling applies; it
    is exactly the attribute ``Document.insert`` sets at document.py:295.
    """
    doc = _stored(doctype, **fields)
    setattr(doc, "__islocal", True)
    return doc


# (DocType, handler, in-scope fields, out-of-scope fields, project-less fields).
# The anchor is the doc's own `project` everywhere except Passenger Manifest, which
# carries no project column and resolves through its Route Plan.
_PROJECT_ANCHOR = ({"project": PROJ_A}, {"project": PROJ_B}, {"project": None})
_MANIFEST_ANCHOR = (
    {"route_plan": "RP-A", "dispatch_trip": None},
    {"route_plan": "RP-B", "dispatch_trip": None},
    {"route_plan": None, "dispatch_trip": None},
)

# The one DocType whose model forbids a project-less row: Fuel Claim marks `project`
# reqd. test_every_tightened_doctype_really_marks_project_reqd holds that to the JSON.
TIGHTENED_CASES = [("Fuel Claim", SP.scoped_has_permission, *_PROJECT_ANCHOR)]

# The ten left alone; the per-DocType reason each one's project-less create is a real
# business state is in the PROJECT_MANDATORY_ON_CREATE survey (permissions.py).
UNCHANGED_CASES = [
    ("Vehicle Assignment", SP.scoped_has_permission, *_PROJECT_ANCHOR),
    ("Fuel Request", SP.scoped_has_permission, *_PROJECT_ANCHOR),
    ("Transport Request", SP.scoped_has_permission, *_PROJECT_ANCHOR),
    ("Route Plan", SP.scoped_has_permission, *_PROJECT_ANCHOR),
    ("Issue", SP.scoped_has_permission, *_PROJECT_ANCHOR),
    ("Fuel Quota", SP.scoped_has_permission, *_PROJECT_ANCHOR),
    ("Fuel Exception Case", SP.scoped_has_permission, *_PROJECT_ANCHOR),
    ("Salis Vehicle", SP.scoped_has_permission, *_PROJECT_ANCHOR),
    ("Passenger Manifest", SP.scoped_has_permission, *_MANIFEST_ANCHOR),
    ("Salis Payment Request", SP.payment_sod_has_permission, *_PROJECT_ANCHOR),
]

ALL_CASES = TIGHTENED_CASES + UNCHANGED_CASES


class _ScopeCase(unittest.TestCase):
    """A constructed session, db and scope, and no site anywhere."""

    def setUp(self):
        self._stub_local("session", frappe._dict(user=CREATOR))
        self._stub_local("db", SimpleNamespace(get_value=self._get_value))

    def _stub_local(self, name, value):
        """Install a stub on ``frappe.local``, queueing its restore BEFORE the write.

        ``frappe.db`` / ``frappe.session`` are proxies onto ``frappe.local``, so a stub
        left installed is inherited by every later test in the run; registering the
        cleanup after the mutation would strand it if anything in between throws.
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
    def _get_value(doctype, name, fieldname):
        if doctype == "Route Plan" and fieldname == "project":
            return ROUTE_PLANS.get(name)
        if doctype == "Dispatch Trip":
            return TRIPS.get(name, {}).get(fieldname)
        return None

    def _resolvers(self, **values):
        """Point the module's scope resolvers at ``values`` for this test only.

        Each cleanup is registered BEFORE its patcher starts, for the same reason
        ``_stub_local`` does it: a throw between the two would otherwise strand the patch
        on the module for every later test in the run.
        """
        for attr, value in values.items():
            patcher = patch.object(SP, attr, return_value=value)
            self.addCleanup(patcher.stop)
            patcher.start()

    def scoped(self, projects=(PROJ_A,)):
        self._resolvers(_is_unscoped=False, _allowed_projects=list(projects))

    def unscoped(self):
        self._resolvers(_is_unscoped=True)


class TestTheTightenedDocTypeSeparatesItsVerdicts(_ScopeCase):
    """Proof 1 — the two verdicts, creator as owner in every one of them."""

    def test_an_in_scope_create_is_allowed(self):
        self.scoped()
        for label, handler, in_scope, _out, _none in TIGHTENED_CASES:
            with self.subTest(doctype=label):
                doc = _unsaved(label, **in_scope)
                self.assertEqual(doc.owner, CREATOR)
                self.assertIsNone(
                    handler(doc, "create"),
                    f"{label}: a scoped user cannot create inside their own project",
                )

    def test_an_out_of_scope_create_is_refused(self):
        self.scoped()
        for label, handler, _in, out_of_scope, _none in TIGHTENED_CASES:
            with self.subTest(doctype=label):
                doc = _unsaved(label, **out_of_scope)
                self.assertEqual(doc.owner, CREATOR)
                self.assertIs(
                    handler(doc, "create"),
                    False,
                    f"{label}: a scoped user created under another project",
                )

    def test_a_project_less_create_is_refused(self):
        """The A-250 leak itself: the creator owns the row, so ownership must not decide."""
        self.scoped()
        for label, handler, _in, _out, unanchored in TIGHTENED_CASES:
            with self.subTest(doctype=label):
                doc = _unsaved(label, **unanchored)
                self.assertEqual(doc.owner, CREATOR)
                self.assertIs(
                    handler(doc, "create"),
                    False,
                    f"{label}: a scoped user created an unanchored row and owned it",
                )

    def test_the_two_verdicts_are_never_the_same_verdict(self):
        """Fails on either collapse — allow-everything AND block-everything.

        Both pairs are checked: in-scope against out-of-scope (the A-233 shape) and
        in-scope against project-less (the A-250 shape).
        """
        self.scoped()
        for label, handler, in_scope, out_of_scope, unanchored in TIGHTENED_CASES:
            with self.subTest(doctype=label):
                allowed = handler(_unsaved(label, **in_scope), "create")
                refused_out = handler(_unsaved(label, **out_of_scope), "create")
                refused_none = handler(_unsaved(label, **unanchored), "create")
                self.assertEqual(
                    (allowed, refused_out), (None, False), f"{label}: verdicts collapsed"
                )
                self.assertEqual(
                    (allowed, refused_none), (None, False), f"{label}: verdicts collapsed"
                )
                self.assertNotEqual(allowed, refused_out)
                self.assertNotEqual(allowed, refused_none)

    def test_a_scoped_user_holding_no_project_is_refused_too(self):
        self.scoped(projects=())
        for label, handler, in_scope, _out, _none in TIGHTENED_CASES:
            with self.subTest(doctype=label):
                self.assertIs(handler(_unsaved(label, **in_scope), "create"), False)

    def test_oversight_still_defers(self):
        self.unscoped()
        for label, handler, _in, _out, unanchored in TIGHTENED_CASES:
            with self.subTest(doctype=label):
                self.assertIsNone(handler(_unsaved(label, **unanchored), "create"))


class TestOwnershipStillDecidesAStoredRow(_ScopeCase):
    """Proof 2 — the change is confined to the create check.

    Same document, same missing project, same owner; only the unsaved flag differs. A
    project-less row that already EXISTS is still readable by the user who owns it, which
    is what every project-less row in the database depends on today.
    """

    def test_the_owner_may_still_act_on_their_own_stored_project_less_row(self):
        self.scoped()
        for label, handler, _in, _out, unanchored in ALL_CASES:
            with self.subTest(doctype=label):
                self.assertIsNone(
                    handler(_stored(label, **unanchored), "read"),
                    f"{label}: the owner lost access to their own stored row",
                )

    def test_a_non_owner_is_still_denied_a_stored_project_less_row(self):
        self.scoped()
        for label, handler, _in, _out, unanchored in ALL_CASES:
            with self.subTest(doctype=label):
                doc = _stored(label, owner=STRANGER, **unanchored)
                self.assertIs(handler(doc, "read"), False)

    def test_a_doc_carrying_no_flag_is_treated_as_stored(self):
        """The flag is the whole discriminator, so pin what its absence means.

        ``Document.insert`` deletes ``__islocal`` once the row is written
        (document.py:338), so a doc read back from the database never carries it.
        """
        self.scoped()
        doc = _stored("Fuel Claim", project=None)
        self.assertFalse(hasattr(doc, "__islocal"))
        self.assertFalse(SP._is_unsaved(doc))
        self.assertIsNone(SP.scoped_has_permission(doc, "create"))


class TestTheOtherTenKeepTheirProjectLessCreate(_ScopeCase):
    """Proof 3 — the blackout that made A-250 not worth fixing blanket did not happen.

    Every DocType left out of the set must still admit a project-less create, and must
    still refuse an out-of-scope one — so "left alone" means untouched, not unguarded.
    """

    def test_a_project_less_create_still_passes(self):
        self.scoped()
        for label, handler, _in, _out, unanchored in UNCHANGED_CASES:
            with self.subTest(doctype=label):
                self.assertIsNone(
                    handler(_unsaved(label, **unanchored), "create"),
                    f"{label}: a legitimate project-less create was blacked out",
                )

    def test_an_out_of_scope_create_is_still_refused(self):
        self.scoped()
        for label, handler, _in, out_of_scope, _none in UNCHANGED_CASES:
            with self.subTest(doctype=label):
                doc = _unsaved(label, **out_of_scope)
                self.assertEqual(doc.owner, CREATOR)
                self.assertIs(
                    handler(doc, "create"),
                    False,
                    f"{label}: the project boundary was lost",
                )

    def test_those_two_verdicts_never_collapse_either(self):
        self.scoped()
        for label, handler, in_scope, out_of_scope, unanchored in UNCHANGED_CASES:
            with self.subTest(doctype=label):
                verdicts = (
                    handler(_unsaved(label, **in_scope), "create"),
                    handler(_unsaved(label, **out_of_scope), "create"),
                    handler(_unsaved(label, **unanchored), "create"),
                )
                self.assertEqual((verdicts[0], verdicts[1]), (None, False))
                self.assertIsNone(verdicts[2])


class TestTheHandlerStaysPtypeAgnostic(_ScopeCase):
    """Proof 4 — the contract the obvious fix would have broken.

    ``scoped_has_permission`` is deny-only and ptype-agnostic by contract: the same
    denial applies to every action. Branching on ``ptype`` was the tempting fix;
    branching on the document's storage state is not the same thing.
    """

    PTYPES = ("create", "read", "write", "submit", "cancel", "delete")

    def test_no_ptype_changes_any_verdict(self):
        self.scoped()
        for label, handler, in_scope, out_of_scope, unanchored in TIGHTENED_CASES:
            for ptype in self.PTYPES:
                with self.subTest(doctype=label, ptype=ptype):
                    self.assertIsNone(handler(_unsaved(label, **in_scope), ptype))
                    self.assertIs(handler(_unsaved(label, **out_of_scope), ptype), False)
                    self.assertIs(handler(_unsaved(label, **unanchored), ptype), False)

    def test_every_verdict_is_deny_only(self):
        """A handler may return False (block) or None (defer) — never a grant."""
        self.scoped()
        for label, handler, in_scope, out_of_scope, unanchored in ALL_CASES:
            for fields in (in_scope, out_of_scope, unanchored):
                for build in (_unsaved, _stored):
                    with self.subTest(doctype=label, build=build.__name__, fields=fields):
                        verdict = handler(build(label, **fields), "create")
                        self.assertIn(verdict, (None, False))


class TestTheGuardIsLoadBearing(_ScopeCase):
    """Proof 5 — neutralise the guard two different ways and the leak must come back.

    A regression test that cannot fail is worthless. Forcing ``_is_unsaved`` to False
    reproduces the pre-A-250 handler exactly (ownership tested first, unconditionally);
    emptying the set reproduces the deliberate not-fixed state. Both must re-admit the
    project-less create, or the proofs above are not testing what they claim.
    """

    def test_neutralising_the_unsaved_check_reopens_the_leak(self):
        self.scoped()
        with patch.object(SP, "_is_unsaved", return_value=False):
            for label, handler, _in, _out, unanchored in TIGHTENED_CASES:
                with self.subTest(doctype=label):
                    self.assertIsNone(
                        handler(_unsaved(label, **unanchored), "create"),
                        f"{label}: the pre-fix leak no longer reproduces",
                    )

    def test_emptying_the_doctype_set_reopens_the_leak(self):
        self.scoped()
        with patch.object(SP, "PROJECT_MANDATORY_ON_CREATE", frozenset()):
            for label, handler, _in, _out, unanchored in TIGHTENED_CASES:
                with self.subTest(doctype=label):
                    self.assertIsNone(
                        handler(_unsaved(label, **unanchored), "create"),
                        f"{label}: the set is not what decides the verdict",
                    )

    def test_adding_a_doctype_to_the_set_would_deny_it(self):
        """The set is the whole switch, so prove it switches — and prove, by the same
        stroke, that every DocType left out was left out by choice and not by accident."""
        self.scoped()
        label, handler, _in, _out, unanchored = UNCHANGED_CASES[0]
        self.assertIsNone(handler(_unsaved(label, **unanchored), "create"))
        with patch.object(SP, "PROJECT_MANDATORY_ON_CREATE", frozenset({label})):
            self.assertIs(handler(_unsaved(label, **unanchored), "create"), False)


class TestTheSetIsHeldToTheModelAndTheWiring(unittest.TestCase):
    """Proof 6 — the survey cannot rot silently.

    The set's whole justification is that the DocType's OWN metadata marks ``project``
    mandatory, so the desk can never produce a project-less create and only a
    mandatory-skipping programmatic insert is denied. If that stops being true — the flag
    is dropped, or a DocType is added without it — the justification is gone and this
    fails. The wiring check pins the eleven DocTypes the survey covered.
    """

    APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(SP.__file__)))

    def _doctype_json(self, doctype):
        slug = doctype.lower().replace(" ", "_").replace("-", "_")
        path = os.path.join(self.APP_ROOT, "salis", "doctype", slug, slug + ".json")
        self.assertTrue(
            os.path.exists(path),
            f"{doctype} is in PROJECT_MANDATORY_ON_CREATE but this app does not own its "
            "DocType JSON, so the reqd justification cannot be checked",
        )
        with open(path) as handle:
            return json.load(handle)

    def test_the_set_is_not_empty(self):
        self.assertTrue(SP.PROJECT_MANDATORY_ON_CREATE)

    def test_every_tightened_doctype_really_marks_project_reqd(self):
        for doctype in SP.PROJECT_MANDATORY_ON_CREATE:
            with self.subTest(doctype=doctype):
                fields = self._doctype_json(doctype).get("fields", [])
                project = next(
                    (f for f in fields if f.get("fieldname") == "project"), None
                )
                self.assertIsNotNone(project, f"{doctype} has no project field")
                self.assertEqual(
                    project.get("reqd"),
                    1,
                    f"{doctype}: project is no longer mandatory, so denying its "
                    "project-less create now blacks out an ordinary desk save",
                )

    def test_the_surveyed_doctypes_are_still_the_wired_ones(self):
        """Every DocType routed to this handler must appear in the survey above."""
        from apex import hooks

        wired = {
            doctype
            for doctype, target in hooks.has_permission.items()
            if target
            in (
                "apex.salis.permissions.scoped_has_permission",
                "apex.salis.permissions.payment_sod_has_permission",
            )
        }
        self.assertEqual(
            wired,
            {label for label, *_ in ALL_CASES},
            "the DocTypes wired to scoped_has_permission changed; redo the "
            "per-DocType survey before trusting PROJECT_MANDATORY_ON_CREATE",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
