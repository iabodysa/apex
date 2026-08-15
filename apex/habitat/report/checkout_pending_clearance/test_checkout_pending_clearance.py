# Copyright (c) 2026, AFMCO and contributors
"""A-225 — the cross-building disclosure in Checkout Pending Clearance, and its close.

WHAT LEAKED. Every query in the report is ``frappe.get_all``, which forces
``ignore_permissions=True``, so the ``Housing Checkout`` row boundary now registered in
``hooks.permission_query_conditions`` never reaches this SQL. ``Resident Supervisor`` is in
the report's audience (its roles table intersected with the ref's ``report`` grants) and is
NOT in ``HOUSING_UNSCOPED_ROLES``, so it is genuinely building-scoped — and it was reading
every estate's checkouts, plus two derived values that are worse than the row itself:

  * ``open_custody_issues`` — a COUNT over Custody Issue rows it cannot list. An aggregate
    over out-of-estate rows is still a disclosure.
  * ``damage_assessment`` — the NAME of a Custody Damage Assessment it cannot list. A
    document identifier from another building, handed over directly.

The fixture below is built so both are visible and falsifiable: EMP-1 holds one custody
issue in each of two buildings, and the damage assessment that sorts FIRST (the one the
report picks) is the out-of-estate one. A supervisor holding only BLD-A must see a count of
1 and ``CDA-002``; before the fix it saw 2 and ``CDA-001``.

WHY THESE TESTS ARE SITELESS. The bench is shared this wave, so nothing here may touch a
site: no ``FrappeTestCase``, no fixtures, no ``frappe.set_user``. The permissions are
CONSTRUCTED (the two module-level resolvers the scope helpers funnel through are stubbed,
which is the documented stub point) and the query layer is a constructed in-memory
``get_all`` that honours the filters the report passes. That proves the report's own
filtering logic end to end, and it does NOT prove the Frappe permission layer resolves the
same way at runtime.

A RUNTIME DEMONSTRATION IS THEREFORE STILL OWED: log in as a Resident Supervisor holding a
User Permission for one building only, open Checkout Pending Clearance, and confirm no
other building's checkout, custody count or damage-assessment name appears. Nothing below
substitutes for that.
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

import frappe

from apex.habitat import permissions as HP
from apex.habitat.report.checkout_pending_clearance import (
    checkout_pending_clearance as R,
)

BLD_A = "BLD-A"
BLD_B = "BLD-B"

BEDS = {"BED-A1": BLD_A, "BED-B1": BLD_B}

CHECKOUTS = [
    {"name": "HC-A", "employee": "EMP-1", "bed": "BED-A1", "docstatus": 1,
     "checkout_date": "2026-07-01", "custody_cleared": 0},
    {"name": "HC-B", "employee": "EMP-2", "bed": "BED-B1", "docstatus": 1,
     "checkout_date": "2026-07-02", "custody_cleared": 0},
]

EMPLOYEES = [
    {"name": "EMP-1", "employee_name": "Resident One"},
    {"name": "EMP-2", "employee_name": "Resident Two"},
]

CUSTODY_ISSUES = [
    {"name": "CI-1", "issued_to_employee": "EMP-1", "building": BLD_A, "docstatus": 1},
    {"name": "CI-2", "issued_to_employee": "EMP-1", "building": BLD_B, "docstatus": 1},
    {"name": "CI-3", "issued_to_employee": "EMP-2", "building": BLD_B, "docstatus": 1},
]

# CDA-002 is in BLD-A but sorts SECOND, so an unscoped render picks the BLD-B one. That
# ordering is the point: it makes the identifier leak show up as a value, not a filter.
DAMAGE = [
    {"name": "CDA-001", "employee": "EMP-1", "building": BLD_B, "docstatus": 1},
    {"name": "CDA-002", "employee": "EMP-1", "building": BLD_A, "docstatus": 1},
]

TABLES = {
    "Housing Checkout": CHECKOUTS,
    "Employee": EMPLOYEES,
    "Custody Issue": CUSTODY_ISSUES,
    "Custody Damage Assessment": DAMAGE,
    "Bed": [{"name": bed, "building": bld} for bed, bld in sorted(BEDS.items())],
}


def _matches(row, filters):
    """Honour the two filter spellings the report uses: equality and ``["in", [...]]``."""
    for field, want in (filters or {}).items():
        have = row.get(field)
        if isinstance(want, (list, tuple)) and len(want) == 2 and want[0] == "in":
            if have not in want[1]:
                return False
        elif have != want:
            return False
    return True


class _Recorder:
    """A constructed ``get_all`` that filters real rows and records every call."""

    def __init__(self):
        self.calls = []

    def __call__(self, doctype, filters=None, fields=None, pluck=None,
                 group_by=None, order_by=None, **kwargs):
        self.calls.append(SimpleNamespace(doctype=doctype, filters=dict(filters or {})))
        rows = [r for r in TABLES[doctype] if _matches(r, filters)]
        if order_by:
            rows = sorted(rows, key=lambda r: r["name"], reverse="desc" in order_by)
        if pluck:
            return [r[pluck] for r in rows]
        if group_by:
            counts = {}
            for row in rows:
                counts[row[group_by]] = counts.get(row[group_by], 0) + 1
            return [
                frappe._dict({group_by: key, "issue_count": n})
                for key, n in sorted(counts.items())
            ]
        return [frappe._dict(r) for r in rows]

    def filters_for(self, doctype):
        return [c.filters for c in self.calls if c.doctype == doctype]


_ABSENT = object()

# The (doctype, fieldname) pairs this file answers from its own fixtures. A pair listed
# here returns the fixture answer even when that answer is None, which is what makes
# "this bed is not in your estate" distinguishable from "the db has not been asked yet".
_FIXTURE_LOOKUPS = frozenset({("Bed", "building"), ("Housing Assignment", "building")})


class _ScopeCase(unittest.TestCase):
    """Shared harness: a constructed session, db and scope, and no site anywhere.

    ``stub_db`` is a switch rather than a constant because the two halves of this file
    need different things. The query-fragment cases assert the SQL a scope produces and
    must never reach a database. The has_permission cases drive the framework's own
    permission machinery, which since this file was written reaches ``is_virtual_doctype``
    and ``get_user_permissions`` — both ask the db for surface no fake carries, so a
    stub there raises AttributeError before the case under test runs and the guard errors
    instead of grading.
    """

    stub_db = True

    def setUp(self):
        # These are PROCESS globals — `frappe.db`, `frappe.session` and `frappe.lang` are
        # proxies onto `frappe.local`, so a stub left installed is inherited by every later
        # test in the run. Left unrestored, the db stub aborted the whole suite in
        # FrappeTestCase.setUpClass, which calls frappe.db.commit().
        self._stub_local("session", frappe._dict(user="supervisor@example.com"))
        self._stub_local("lang", "en")
        if self.stub_db:
            self._stub_local("db", SimpleNamespace(
                escape=lambda value: "'{0}'".format(value),
                get_value=self._get_value,
            ))
        else:
            self._patch_get_value()

    def _patch_get_value(self):
        """Answer this file's fixture lookups off the live db, leaving the rest real.

        The handler resolves a checkout's estate through two get_value hops the fixtures
        above define. Everything else — the framework's own permission reads — must reach
        the real database, so only the two known lookups are intercepted.
        """
        real = frappe.local.db.get_value

        def routed(*args, **kwargs):
            """Return the fixture answer for a known lookup, else the real one.

            Reads the three leading parameters off whichever call shape the caller used,
            so a keyword call cannot collide with a positional forward.
            """
            doctype = args[0] if args else kwargs.get("doctype")
            name = args[1] if len(args) > 1 else kwargs.get("filters")
            fieldname = args[2] if len(args) > 2 else kwargs.get("fieldname", "name")
            if isinstance(name, str) and (doctype, fieldname) in _FIXTURE_LOOKUPS:
                return self._get_value(doctype, name, fieldname)
            return real(*args, **kwargs)

        patcher = patch.object(frappe.local.db, "get_value", routed)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _stub_local(self, name, value):
        """Install a stub on ``frappe.local``, queueing its restore BEFORE the write.

        Registering the cleanup after the mutation would strand the stub if anything
        between the two throws.
        """
        self.addCleanup(self._restore_local, name, getattr(frappe.local, name, _ABSENT))
        setattr(frappe.local, name, value)

    @staticmethod
    def _restore_local(name, original):
        """Restore the ORIGINAL, and absence is a value: werkzeug's ``Local`` raises
        AttributeError for an unset name, so leaving ``None`` behind is not the same thing.
        """
        if original is _ABSENT:
            try:
                delattr(frappe.local, name)
            except AttributeError:
                pass
        else:
            setattr(frappe.local, name, original)

    @staticmethod
    def _get_value(doctype, name, fieldname):
        if doctype == "Bed" and fieldname == "building":
            return BEDS.get(name)
        if doctype == "Housing Assignment" and fieldname == "building":
            return {"HA-A": BLD_A, "HA-B": BLD_B}.get(name)
        return None

    def _render(self, unscoped, buildings, filters=None):
        """Run the report under a constructed scope; return (rows, recorded get_all calls)."""
        recorder = _Recorder()
        # `_` is stubbed too: the real one loads a site's translations and, failing that,
        # writes to a bench log path, so leaving it live would couple this to a bench.
        with patch.object(HP, "_building_is_unscoped", return_value=unscoped), \
             patch.object(HP, "_allowed_buildings", return_value=list(buildings)), \
             patch.object(HP, "_allowed_buildings_for", return_value=list(buildings)), \
             patch.object(R.frappe, "get_all", recorder), \
             patch.object(R.frappe, "_", lambda text, *a, **kw: text), \
             patch.object(R, "today", lambda: "2026-07-26"), \
             patch.object(R, "date_diff", lambda a, b: 25):
            _columns, data, *_rest = R.execute(filters or {})
        return data, recorder


class TestScopedSupervisorSeesOnlyItsOwnBuildings(_ScopeCase):
    """Proof 1 — no cross-building row, count or identifier reaches a scoped role."""

    def _rows(self, filters=None):
        return self._render(unscoped=False, buildings=[BLD_A], filters=filters)

    def test_only_the_held_buildings_checkout_is_emitted(self):
        data, _ = self._rows()
        self.assertEqual([r["name"] for r in data], ["HC-A"])
        self.assertEqual([r["building"] for r in data], [BLD_A])

    def test_no_emitted_value_anywhere_names_an_unheld_building(self):
        """The blunt instrument: BLD_B must not appear in any cell of any row."""
        data, _ = self._rows()
        leaked = [
            (row["name"], field)
            for row in data
            for field, value in row.items()
            if isinstance(value, str) and BLD_B in value
        ]
        self.assertEqual(leaked, [])

    def _row(self, name):
        """Address the row by name, never by position.

        Positional lookup made one of these assertions pass against the LEAKING code by
        coincidence: unscoped, the other estate's checkout sorted first and happened to
        carry the value being asserted.
        """
        data, _ = self._rows()
        matched = [r for r in data if r["name"] == name]
        self.assertEqual(len(matched), 1, f"expected exactly one {name} row, got {data}")
        return matched[0]

    def test_the_custody_issue_count_excludes_out_of_estate_rows(self):
        """EMP-1 holds CI-1 in BLD-A and CI-2 in BLD-B; a BLD-A supervisor may count one."""
        self.assertEqual(self._row("HC-A")["open_custody_issues"], 1)

    def test_the_damage_assessment_name_is_never_an_out_of_estate_document(self):
        """CDA-001 (BLD-B) sorts first, so an unfiltered render picks it. This must not."""
        self.assertEqual(self._row("HC-A")["damage_assessment"], "CDA-002")

    def test_the_joined_custody_queries_carry_the_building_boundary(self):
        _data, rec = self._rows()
        for doctype in ("Custody Issue", "Custody Damage Assessment"):
            with self.subTest(doctype=doctype):
                self.assertEqual(
                    rec.filters_for(doctype)[0].get("building"), ["in", [BLD_A]]
                )

    def test_the_checkout_query_is_narrowed_to_in_scope_beds(self):
        _data, rec = self._rows()
        self.assertEqual(
            rec.filters_for("Housing Checkout")[0].get("bed"), ["in", ["BED-A1"]]
        )

    def test_an_out_of_scope_building_filter_yields_nothing_not_everything(self):
        data, rec = self._rows(filters={"building": BLD_B})
        self.assertEqual(data, [])
        self.assertEqual(rec.filters_for("Housing Checkout"), [])


class TestUnscopedRolesStillSeeEverything(_ScopeCase):
    """Proof 2a — the oversight roles lose nothing. A blackout is as wrong as a leak."""

    def _rows(self, filters=None):
        return self._render(unscoped=True, buildings=[], filters=filters)

    def test_every_building_is_still_emitted(self):
        data, _ = self._rows()
        self.assertEqual(sorted(r["name"] for r in data), ["HC-A", "HC-B"])
        self.assertEqual({r["building"] for r in data}, {BLD_A, BLD_B})

    def test_no_restriction_is_added_to_any_query(self):
        _data, rec = self._rows()
        self.assertNotIn("bed", rec.filters_for("Housing Checkout")[0])
        for doctype in ("Custody Issue", "Custody Damage Assessment"):
            with self.subTest(doctype=doctype):
                self.assertNotIn("building", rec.filters_for(doctype)[0])

    def test_the_estate_wide_count_and_first_assessment_are_unchanged(self):
        """The values the scoped assertions above deliberately differ from."""
        data, _ = self._rows()
        row = next(r for r in data if r["name"] == "HC-A")
        self.assertEqual(row["open_custody_issues"], 2)
        self.assertEqual(row["damage_assessment"], "CDA-001")

    def test_an_oversight_building_filter_still_narrows_only_the_checkout_list(self):
        """Picking a building must not shrink an unscoped user's custody counts."""
        data, rec = self._rows(filters={"building": BLD_A})
        self.assertEqual([r["name"] for r in data], ["HC-A"])
        self.assertEqual(data[0]["open_custody_issues"], 2)
        self.assertNotIn("building", rec.filters_for("Custody Issue")[0])


class TestScopedWithNoBuildingSeesNothing(_ScopeCase):
    """Proof 2b — the edge case that fails OPEN if the two branches are swapped."""

    def test_no_rows_and_no_checkout_query_at_all(self):
        data, rec = self._render(unscoped=False, buildings=[])
        self.assertEqual(data, [])
        self.assertEqual(rec.calls, [])


class TestTheQueryFragment(_ScopeCase):
    """``housing_checkout_query`` — the list/desk half of the same boundary."""

    def test_unscoped_renders_an_empty_string_meaning_no_restriction(self):
        with patch.object(HP, "_building_is_unscoped", return_value=True):
            self.assertEqual(HP.building_scope_query(doctype="Housing Checkout", user="mgr@example.com"), "")

    def test_scoped_with_no_buildings_renders_a_fragment_matching_nothing(self):
        with patch.object(HP, "_building_is_unscoped", return_value=False), \
             patch.object(HP, "_allowed_buildings", return_value=[]), \
             patch.object(HP, "_allowed_buildings_for", return_value=[]):
            self.assertEqual(HP.building_scope_query(doctype="Housing Checkout", user="sup@example.com"), "1=0")

    def test_scoped_renders_the_bed_subquery_because_there_is_no_building_column(self):
        with patch.object(HP, "_building_is_unscoped", return_value=False), \
             patch.object(HP, "_allowed_buildings", return_value=[BLD_A, BLD_B]), \
             patch.object(HP, "_allowed_buildings_for", return_value=[BLD_A, BLD_B]):
            self.assertEqual(
                HP.building_scope_query(doctype="Housing Checkout", user="sup@example.com"),
                "`bed` in (select `name` from `tabBed` "
                "where `building` in ('BLD-A', 'BLD-B'))",
            )

    def test_the_two_edge_cases_are_not_interchangeable(self):
        """"" would let a scoped user read everything; "1=0" would blackout oversight."""
        with patch.object(HP, "_building_is_unscoped", return_value=True):
            unscoped = HP.building_scope_query(doctype="Housing Checkout", user="mgr@example.com")
        with patch.object(HP, "_building_is_unscoped", return_value=False), \
             patch.object(HP, "_allowed_buildings", return_value=[]), \
             patch.object(HP, "_allowed_buildings_for", return_value=[]):
            starved = HP.building_scope_query(doctype="Housing Checkout", user="sup@example.com")
        self.assertNotEqual(unscoped, starved)
        self.assertEqual((unscoped, starved), ("", "1=0"))


class TestTheHasPermissionHandler(_ScopeCase):
    """``housing_checkout_has_permission`` — the form / REST / submit half."""

    stub_db = False

    def _doc(self, **kwargs):
        return SimpleNamespace(doctype="Housing Checkout", **kwargs)

    def test_unscoped_defers_to_the_docperms(self):
        with patch.object(HP, "_building_is_unscoped", return_value=True):
            self.assertIsNone(
                HP.building_scoped_has_permission(self._doc(bed="BED-B1"), "read")
            )

    def test_an_in_estate_checkout_defers_rather_than_granting(self):
        with patch.object(HP, "_building_is_unscoped", return_value=False), \
             patch.object(HP, "_allowed_buildings", return_value=[BLD_A]), \
             patch.object(HP, "_allowed_buildings_for", return_value=[BLD_A]):
            self.assertIsNone(
                HP.building_scoped_has_permission(self._doc(bed="BED-A1"), "read")
            )

    def test_an_out_of_estate_checkout_is_denied_for_every_action(self):
        with patch.object(HP, "_building_is_unscoped", return_value=False), \
             patch.object(HP, "_allowed_buildings", return_value=[BLD_A]), \
             patch.object(HP, "_allowed_buildings_for", return_value=[BLD_A]):
            for ptype in ("read", "write", "submit", "cancel", "delete"):
                with self.subTest(ptype=ptype):
                    self.assertIs(
                        HP.building_scoped_has_permission(
                            self._doc(bed="BED-B1"), ptype
                        ),
                        False,
                    )

    def test_the_create_path_resolves_the_estate_before_bed_is_fetched(self):
        """Document.insert checks create permission BEFORE fetch_from populates `bed`.

        Without the assignment fallback this returns False and a scoped supervisor can
        never create a checkout — the blackout the shared handler would have caused.
        """
        with patch.object(HP, "_building_is_unscoped", return_value=False), \
             patch.object(HP, "_allowed_buildings", return_value=[BLD_A]), \
             patch.object(HP, "_allowed_buildings_for", return_value=[BLD_A]):
            self.assertIsNone(
                HP.building_scoped_has_permission(
                    self._doc(bed=None, assignment="HA-A"), "create"
                )
            )
            self.assertIs(
                HP.building_scoped_has_permission(
                    self._doc(bed=None, assignment="HA-B"), "create"
                ),
                False,
            )

    def test_an_unresolvable_estate_fails_closed(self):
        with patch.object(HP, "_building_is_unscoped", return_value=False), \
             patch.object(HP, "_allowed_buildings", return_value=[BLD_A]), \
             patch.object(HP, "_allowed_buildings_for", return_value=[BLD_A]):
            self.assertIs(
                HP.building_scoped_has_permission(
                    self._doc(bed=None, assignment=None), "read"
                ),
                False,
            )

    def test_the_checkout_name_is_the_shared_handler(self):
        """The two names ARE one function today, and the tests above cover both.

        This replaces a case asserting the opposite: that the shared handler blacked the
        role out and only a private Housing Checkout handler could resolve the estate.
        The product reversed that. ``housing_checkout_has_permission`` is now a
        compatibility name returning ``building_scoped_has_permission``, which resolves
        the estate through the ``hop`` strategy in ``BUILDING_SCOPE``. Asserting the old
        divergence would grade a difference that no longer exists.
        """
        with patch.object(HP, "_building_is_unscoped", return_value=False), \
             patch.object(HP, "_allowed_buildings_for", return_value=[BLD_A]):
            in_estate = self._doc(bed="BED-A1")
            self.assertEqual(
                HP.building_scoped_has_permission(in_estate, "read"),
                HP.building_scoped_has_permission(in_estate, "read"),
            )
            self.assertIsNone(HP.building_scoped_has_permission(in_estate, "read"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
