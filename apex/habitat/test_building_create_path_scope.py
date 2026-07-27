# Copyright (c) 2026, AFMCO and contributors
"""A-229 — the create-path ordering hazard in ``building_scoped_has_permission``.

``Document.insert`` runs ``check_permission("create")`` (frappe/model/document.py:300)
BEFORE ``_validate_links()`` (:302) applies ``fetch_from``. Nine Habitat DocTypes carry a
``building`` that is fetched from a parent link, so at the create check it is EMPTY, the
handler read None, and a building-scoped supervisor was denied the creation of a record in
their OWN estate. Marking ``building`` ``reqd`` does not help — mandatory fields are
enforced in ``_validate()`` (:310), long after the permission check.

Every test below proves the fix BOTH ways, because a handler that lets everything through
on create is worse than one that blocks it: the fetched field empty and the anchor IN
estate must defer, and the same shape with an OUT-OF-ESTATE anchor must still be refused.

WHY THESE TESTS ARE SITELESS. The bench is shared, so nothing here touches a site: the two
module-level resolvers the scope helpers funnel through are stubbed (the documented stub
point) and ``frappe.db.get_value`` is a constructed lookup over the tables below.

A RUNTIME DEMONSTRATION IS THEREFORE STILL OWED for every handler touched: log in as a
Resident Supervisor holding a User Permission for one building only, create each of these
records server-side with the fetched ``building`` left unset, and confirm the in-estate one
saves while the out-of-estate one raises PermissionError. Nothing here substitutes for that.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import frappe

import apex
from apex.habitat import permissions as HP

BLD_A = "BLD-A"
BLD_B = "BLD-B"

# parent doctype -> {parent name: the building that parent lives in}
PARENTS = {
    "Room": {"ROOM-A": BLD_A, "ROOM-B": BLD_B},
    "Bed": {"BED-A": BLD_A, "BED-B": BLD_B},
    "Custody Issue": {"CI-A": BLD_A, "CI-B": BLD_B},
    "Custody Return": {"CR-A": BLD_A, "CR-B": BLD_B},
    "Maintenance Request": {"MR-A": BLD_A, "MR-B": BLD_B},
    # Maintenance Inspection Report anchors on `maintenance_work_order`; without a
    # row here _anchor_names raises KeyError and its create-path pair errors out
    # instead of testing anything.
    "Maintenance Work Order": {"MWO-A": BLD_A, "MWO-B": BLD_B},
    "Scheduled Task Assignment": {"STA-A": BLD_A, "STA-B": BLD_B},
    # Room Bed Transfer anchors on `assignment`, so its parent is the assignment,
    # not a room or a bed. Without a row here _anchor_names raises
    # KeyError and the create-path pair errors instead of testing anything.
    "Housing Assignment": {"HA-A": BLD_A, "HA-B": BLD_B},
}

_ABSENT = object()


def _anchor_names(parent_doctype):
    """The (in-estate, out-of-estate) parent for a doctype, ordered by building."""
    rows = PARENTS[parent_doctype]
    return (
        next(n for n, b in rows.items() if b == BLD_A),
        next(n for n, b in rows.items() if b == BLD_B),
    )


class _ScopeCase(unittest.TestCase):
    """A constructed db and scope, and no site anywhere."""

    def setUp(self):
        self._stub_local("session", frappe._dict(user="supervisor@example.com"))
        self._stub_local("db", SimpleNamespace(get_value=self._get_value))

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
    def _get_value(doctype, name, fieldname):
        if fieldname != "building":
            return None
        return PARENTS.get(doctype, {}).get(name)

    def scoped(self):
        """Stub a supervisor who holds BLD_A and nothing else."""
        return self._scope(unscoped=False, buildings=[BLD_A])

    def _scope(self, unscoped, buildings):
        outer = patch.object(HP, "_building_is_unscoped", return_value=unscoped)
        inner = patch.object(HP, "_allowed_buildings", return_value=list(buildings))
        outer.start()
        inner.start()
        self.addCleanup(inner.stop)
        self.addCleanup(outer.stop)
        return None

    @staticmethod
    def doc(doctype, **kwargs):
        kwargs.setdefault("building", None)
        return SimpleNamespace(doctype=doctype, **kwargs)


class TestTheCreatePathResolvesThroughTheAnchor(_ScopeCase):
    """Proof 1 — a create with ``building`` still unfetched is decided on its merits."""

    def test_an_in_estate_anchor_allows_the_create(self):
        self.scoped()
        for doctype, (field, parent_doctype) in HP.BUILDING_FETCH_ANCHOR.items():
            in_estate, _out = _anchor_names(parent_doctype)
            with self.subTest(doctype=doctype):
                self.assertIsNone(
                    HP.building_scoped_has_permission(
                        self.doc(doctype, **{field: in_estate}), "create"
                    ),
                    f"{doctype}: a scoped supervisor cannot create in their own estate",
                )

    def test_an_out_of_estate_anchor_still_refuses_the_create(self):
        """The easy mistake this guards: making create pass by making it pass for all."""
        self.scoped()
        for doctype, (field, parent_doctype) in HP.BUILDING_FETCH_ANCHOR.items():
            _in_estate, out = _anchor_names(parent_doctype)
            with self.subTest(doctype=doctype):
                self.assertIs(
                    HP.building_scoped_has_permission(
                        self.doc(doctype, **{field: out}), "create"
                    ),
                    False,
                    f"{doctype}: a scoped supervisor created into another estate",
                )

    def test_an_unresolvable_estate_still_fails_closed(self):
        """No ``building`` and no anchor is a denial, not a deferral."""
        self.scoped()
        for doctype, (field, _parent) in HP.BUILDING_FETCH_ANCHOR.items():
            with self.subTest(doctype=doctype):
                self.assertIs(
                    HP.building_scoped_has_permission(
                        self.doc(doctype, **{field: None}), "create"
                    ),
                    False,
                )

    def test_the_two_verdicts_are_not_the_same_verdict(self):
        """A handler returning None for both would pass every assertion above but one."""
        self.scoped()
        doctype, (field, parent_doctype) = next(iter(HP.BUILDING_FETCH_ANCHOR.items()))
        in_estate, out = _anchor_names(parent_doctype)
        allowed = HP.building_scoped_has_permission(
            self.doc(doctype, **{field: in_estate}), "create"
        )
        refused = HP.building_scoped_has_permission(
            self.doc(doctype, **{field: out}), "create"
        )
        self.assertNotEqual(allowed, refused)
        self.assertEqual((allowed, refused), (None, False))


class TestTheAnchorNeverWidensAnythingElse(_ScopeCase):
    """Proof 2 — the fallback fires only where the fetched field is genuinely empty."""

    def test_a_populated_building_is_used_verbatim_and_the_anchor_ignored(self):
        """A stored row carries its own estate; an in-estate anchor must not rescue it."""
        self.scoped()
        denied = HP.building_scoped_has_permission(
            self.doc("Bed", building=BLD_B, room="ROOM-A"), "read"
        )
        self.assertIs(denied, False)

    def test_every_action_is_still_denied_out_of_estate_not_just_create(self):
        self.scoped()
        for ptype in ("read", "write", "submit", "cancel", "delete"):
            with self.subTest(ptype=ptype):
                self.assertIs(
                    HP.building_scoped_has_permission(
                        self.doc("Custody Return", custody_issue="CI-B"), ptype
                    ),
                    False,
                )

    def test_an_unanchored_doctype_is_unchanged_and_still_fails_closed(self):
        self.scoped()
        self.assertIs(
            HP.building_scoped_has_permission(self.doc("Cleaning Log"), "create"), False
        )

    def test_oversight_defers_before_any_lookup_is_attempted(self):
        self._scope(unscoped=True, buildings=[])
        self.assertIsNone(
            HP.building_scoped_has_permission(self.doc("Bed", room="ROOM-B"), "create")
        )

    def test_a_scoped_user_holding_no_building_is_denied_through_the_anchor_too(self):
        self._scope(unscoped=False, buildings=[])
        self.assertIs(
            HP.building_scoped_has_permission(self.doc("Bed", room="ROOM-A"), "create"),
            False,
        )

    def test_the_building_doctype_is_still_scoped_on_its_own_name(self):
        """The special case the anchor map must not have displaced."""
        self.scoped()
        self.assertIsNone(
            HP.building_scoped_has_permission(
                SimpleNamespace(doctype="Building", name=BLD_A), "read"
            )
        )
        self.assertIs(
            HP.building_scoped_has_permission(
                SimpleNamespace(doctype="Building", name=BLD_B), "read"
            ),
            False,
        )


class TestTheAnchorMapCoversTheWholeClass(unittest.TestCase):
    """The audit itself, kept runnable — a new fetch_from scope field cannot slip in.

    Reads hooks.py and the DocType JSON off disk (no site) and asserts that every DocType
    wired to ``building_scoped_has_permission`` whose ``building`` is a ``fetch_from`` has
    an anchor. Without this the class regresses the next time a field is made fetched.
    """

    APEX = Path(apex.__file__).parent

    @classmethod
    def setUpClass(cls):
        cls.doctypes = {}
        for path in cls.APEX.rglob("*/doctype/*/*.json"):
            try:
                data = json.loads(path.read_text())
            except ValueError:
                continue
            if data.get("doctype") == "DocType" and data.get("name"):
                cls.doctypes[data["name"]] = data

    def _wired_to_the_building_handler(self):
        from apex import hooks

        return [
            doctype
            for doctype, handler in hooks.has_permission.items()
            if handler.endswith(".building_scoped_has_permission")
        ]

    def test_every_fetched_building_field_has_an_anchor(self):
        unanchored = []
        for doctype in self._wired_to_the_building_handler():
            data = self.doctypes.get(doctype)
            if not data:
                continue
            for field in data.get("fields", []):
                if field.get("fieldname") != "building":
                    continue
                if field.get("fetch_from") and doctype not in HP.BUILDING_FETCH_ANCHOR:
                    unanchored.append((doctype, field["fetch_from"]))
        self.assertEqual(
            unanchored,
            [],
            "these DocTypes scope on a fetch_from building with no create-path anchor",
        )

    def test_no_wired_doctype_lacks_the_building_field_altogether(self):
        """The blackout shape: the shared handler denies its OWN estate without the field.

        Building is the sole legitimate exception — the handler scopes it on ``doc.name``.
        """
        missing = []
        for doctype in self._wired_to_the_building_handler():
            if doctype == "Building":
                continue
            data = self.doctypes.get(doctype)
            if not data:
                continue
            if doctype in HP.BUILDING_FETCH_ANCHOR:
                # Scope resolves through the declared anchor instead of a local
                # `building` field. test_each_anchor_names_a_link_that_actually_exists
                # is what proves that anchor real, so this is a redirect, not an escape.
                continue
            if not any(f.get("fieldname") == "building" for f in data.get("fields", [])):
                missing.append(doctype)
        self.assertEqual(
            missing, [], "these DocTypes are blacked out for their own scoped users"
        )

    def test_each_anchor_names_a_link_that_actually_exists_and_is_not_itself_fetched(self):
        """An anchor that is itself ``fetch_from`` is empty at :300 too, so it fixes nothing."""
        broken = []
        for doctype, (fieldname, parent_doctype) in HP.BUILDING_FETCH_ANCHOR.items():
            data = self.doctypes.get(doctype)
            if not data:
                broken.append((doctype, "doctype json not found"))
                continue
            field = next(
                (f for f in data.get("fields", []) if f.get("fieldname") == fieldname),
                None,
            )
            if field is None:
                broken.append((doctype, f"{fieldname} absent"))
            elif field.get("fetch_from"):
                broken.append((doctype, f"{fieldname} is itself fetched"))
            elif field.get("options") != parent_doctype:
                broken.append((doctype, f"{fieldname} links {field.get('options')}"))
        self.assertEqual(broken, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
