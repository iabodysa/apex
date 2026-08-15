# Copyright (c) 2026, AFMCO and contributors
"""Building row-scoping for Maintenance Inspection Report.

The DocType carries a `building` Link but appeared in NEITHER permission hook dict,
unlike its already-wired sibling Maintenance Work Order. Wiring it needs one extra
step the siblings did not: `building` is `fetch_from maintenance_work_order.building`,
so it is EMPTY at the create check.

WHY THE ANCHOR IS NOT OPTIONAL. `Document.insert` runs `check_permission("create")`
(frappe/model/document.py:300) BEFORE `_validate_links()` (:302) applies `fetch_from`.
Reading `doc.building` alone at that moment yields None, and the shared handler fails
CLOSED on an unresolvable estate — so without a `BUILDING_FETCH_ANCHOR` entry a
building-scoped supervisor could not create an inspection in their OWN estate. `reqd`
does not rescue it: mandatory fields are enforced in `_validate()` (:310), later still.
The anchor names `maintenance_work_order`, the doc's own link, which the payload
carries at :300 and which is not itself fetched.

WHY THE LIST FRAGMENT STILL READS THE COLUMN. Only the create path is early; a row
that reaches `permission_query_conditions` has already been written and always carries
its `building` (reqd + fetch_if_empty). So the fragment is the shared column condition,
no subquery.

WHAT FRAPPE'S NATIVE MATCH LEAVES OPEN, and why the fragment is owed anyway: a scoped
user holding NO Building User Permission gets NO native match condition at all
(db_query.py:1079) and reads every estate, and the non-strict native fragment is
`ifnull(building,'')='' or building in (...)` (db_query.py:1090), which keeps an
empty-building row visible.

SHIPPED PERMISSIONS, HONESTLY. As of this commit the DocType's only DocPerm row is
System Manager, which `HOUSING_UNSCOPED_ROLES` treats as oversight, so at runtime today
no user reaches the scoped branch. The wiring is therefore latent: it is correct the
moment any building-scoped role (Resident Supervisor holds the Safety workspace this
DocType is linked from) is granted read, and it is the create-path anchor that makes
that grant survivable. Nothing here asserts the DocPerm set, because a test that reds
when someone correctly grants that role would be a false alarm.

WHY `frappe.db.sql` AND NOT `frappe.get_list` IN THE RUNTIME CLASS. `get_all` forces
`ignore_permissions` (frappe/__init__.py:2050) so it proves nothing, and `get_list` as
a scoped user would raise PermissionError on a DocType they hold no DocPerm for -- an
empty result that would pass a "the other estate is not returned" assertion for the
wrong reason. Running the fragment the hook injects against the real rows is the same
WHERE clause the desk list builds, with no site permission mutated to observe it.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

import apex
from apex.habitat import permissions as P
from apex.tests.factories import make_scoped_supervisor

DOCTYPE = "Maintenance Inspection Report"
QUERY_FN = "apex.habitat.permissions.building_scope_query"
HANDLER = "apex.habitat.permissions.building_scoped_has_permission"
ANCHOR = ("maintenance_work_order", "Maintenance Work Order")

BLD_A = "MIR-BLD-A"
BLD_B = "MIR-BLD-B"


def _h(n=12):
    return frappe.generate_hash(length=n).upper()


def _scoped_to(buildings):
    """Patch the two module-level resolvers to a scoped user holding ``buildings``."""
    return (
        patch.object(P, "_building_is_unscoped", return_value=False),
        patch.object(P, "_allowed_buildings", return_value=list(buildings)),
    )


class TestMaintenanceInspectionReportScopeWiring(unittest.TestCase):
    """Siteless: the two hook entries, the anchor, and the handler's verdicts."""

    APEX = Path(apex.__file__).parent

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from apex import hooks

        cls.hooks = hooks
        cls.json = json.loads(
            (
                cls.APEX
                / "habitat"
                / "doctype"
                / "maintenance_inspection_report"
                / "maintenance_inspection_report.json"
            ).read_text()
        )

    def _field(self, fieldname):
        return next(
            (f for f in self.json["fields"] if f.get("fieldname") == fieldname), None
        )

    def test_the_list_view_is_wired_to_the_building_fragment(self):
        self.assertEqual(
            self.hooks.permission_query_conditions.get(DOCTYPE),
            QUERY_FN,
            "the inspection list has no building scope",
        )

    def test_the_form_and_rest_paths_are_wired_to_the_shared_handler(self):
        self.assertEqual(
            self.hooks.has_permission.get(DOCTYPE),
            HANDLER,
            "an out-of-estate inspection is still openable",
        )

    def test_both_wired_targets_resolve_to_a_callable(self):
        """A typo in a dotted path fails here, not on a customer site."""
        for dotted in (QUERY_FN, HANDLER):
            with self.subTest(dotted=dotted):
                self.assertTrue(callable(getattr(P, dotted.rsplit(".", 1)[1])))

    def test_the_building_field_is_fetched_and_therefore_owes_an_anchor(self):
        """The premise of the whole card, kept falsifiable.

        If someone later makes `building` a plain Link the anchor becomes dead weight
        and this test says so; while it stays fetched, the anchor is mandatory.
        """
        field = self._field("building")
        self.assertIsNotNone(field)
        self.assertEqual(field.get("options"), "Building")
        self.assertEqual(field.get("fetch_from"), "maintenance_work_order.building")
        self.assertIn(DOCTYPE, P.BUILDING_FETCH_ANCHOR)

    def test_the_anchor_names_a_real_link_that_is_not_itself_fetched(self):
        """An anchor that is itself `fetch_from` is empty at :300 too, so it fixes nothing."""
        self.assertEqual(P.BUILDING_FETCH_ANCHOR[DOCTYPE], ANCHOR)
        fieldname, parent_doctype = ANCHOR
        field = self._field(fieldname)
        self.assertIsNotNone(field, "{0} absent".format(fieldname))
        self.assertEqual(field.get("fieldtype"), "Link")
        self.assertEqual(field.get("options"), parent_doctype)
        self.assertFalse(
            field.get("fetch_from"), "{0} is itself fetched".format(fieldname)
        )

    def test_building_is_the_only_building_link_so_no_link_is_over_restricted(self):
        """Why no field here needs `ignore_user_permissions`.

        A Building User Permission auto-filters EVERY Link whose target is Building
        (db_query.py:1083). That is wanted on the scope axis and silently
        over-restricts on any other Building link. This DocType has exactly one.
        """
        building_links = [
            f["fieldname"]
            for f in self.json["fields"]
            if f.get("fieldtype") == "Link" and f.get("options") == "Building"
        ]
        self.assertEqual(building_links, ["building"])

    def test_a_stored_row_is_judged_on_its_own_building_not_the_anchor(self):
        outer, inner = _scoped_to([BLD_A])
        with outer, inner:
            self.assertIsNone(
                P.building_scoped_has_permission(
                    SimpleNamespace(doctype=DOCTYPE, building=BLD_A), "read", user="sup"
                ),
                "a supervisor was denied their own estate",
            )
            self.assertIs(
                P.building_scoped_has_permission(
                    SimpleNamespace(doctype=DOCTYPE, building=BLD_B), "read", user="sup"
                ),
                False,
                "another estate's inspection was readable",
            )

    def test_the_create_path_resolves_through_the_work_order_both_ways(self):
        """The decisive pair: `building` unfetched, verdict taken from the anchor.

        Paired on purpose — a handler that returned None for both would pass the
        positive half while granting a supervisor every estate on create.
        """
        parents = {"MWO-A": BLD_A, "MWO-B": BLD_B}
        outer, inner = _scoped_to([BLD_A])
        db = SimpleNamespace(
            get_value=lambda dt, name, field: parents.get(name)
            if (dt, field) == (ANCHOR[1], "building")
            else None
        )
        # `patch.object` restores the real connection on exit, exception or not --
        # `frappe.db` is a process global that no test rollback would put back.
        with outer, inner, patch.object(frappe, "db", db):
            allowed = P.building_scoped_has_permission(
                SimpleNamespace(
                    doctype=DOCTYPE, building=None, maintenance_work_order="MWO-A"
                ),
                "create",
                user="sup",
            )
            refused = P.building_scoped_has_permission(
                SimpleNamespace(
                    doctype=DOCTYPE, building=None, maintenance_work_order="MWO-B"
                ),
                "create",
                user="sup",
            )
            unresolvable = P.building_scoped_has_permission(
                SimpleNamespace(
                    doctype=DOCTYPE, building=None, maintenance_work_order=None
                ),
                "create",
                user="sup",
            )
        self.assertEqual(
            (allowed, refused, unresolvable),
            (None, False, False),
            "create-path verdicts collapsed: an in-estate create must defer, an "
            "out-of-estate create must be refused, and no anchor at all must fail closed",
        )

    def test_every_action_is_denied_out_of_estate_not_only_read(self):
        outer, inner = _scoped_to([BLD_A])
        with outer, inner:
            for ptype in ("read", "write", "create", "submit", "cancel", "delete"):
                with self.subTest(ptype=ptype):
                    self.assertIs(
                        P.building_scoped_has_permission(
                            SimpleNamespace(doctype=DOCTYPE, building=BLD_B),
                            ptype,
                            user="sup",
                        ),
                        False,
                    )

    def test_oversight_defers_and_a_permissionless_scoped_user_is_denied(self):
        with patch.object(P, "_building_is_unscoped", return_value=True):
            self.assertIsNone(
                P.building_scoped_has_permission(
                    SimpleNamespace(doctype=DOCTYPE, building=BLD_B), "read", user="mgr"
                )
            )
        outer, inner = _scoped_to([])
        with outer, inner:
            self.assertIs(
                P.building_scoped_has_permission(
                    SimpleNamespace(doctype=DOCTYPE, building=BLD_A), "read", user="sup"
                ),
                False,
            )


class TestMaintenanceInspectionReportScopeRuntime(FrappeTestCase):
    """Needs a bench site: real buildings, real work orders, a real User Permission."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.b1 = cls._building()
        cls.b2 = cls._building()
        cls.scoped = make_scoped_supervisor(cls._user, cls.b1, cls.addClassCleanup)
        # Same role, NO Building User Permission -- the user frappe's native match
        # leaves completely unrestricted.
        cls.unpermitted = cls._user("Resident Supervisor")
        cls.oversight = cls._user("Accommodation Manager")

    @classmethod
    def _building(cls):
        doc = frappe.get_doc({"doctype": "Building", "building_name": "MIR-" + _h()})
        doc.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        cls.addClassCleanup(
            frappe.delete_doc, "Building", doc.name, force=True, ignore_permissions=True
        )
        return doc.name

    @classmethod
    def _user(cls, role):
        email = "mir-{0}@example.com".format(_h()).lower()
        frappe.get_doc(
            {
                "doctype": "User",
                "email": email,
                "first_name": "Scope",
                "send_welcome_email": 0,
                "roles": [{"role": role}],
            }
        ).insert(ignore_permissions=True)
        cls.addClassCleanup(
            frappe.delete_doc, "User", email, force=True, ignore_permissions=True
        )
        return email

    def _work_order(self, building):
        doc = frappe.get_doc(
            {
                "doctype": "Maintenance Work Order",
                "naming_series": "MWO-.YYYY.-.####",
                "building": building,
                "work_description": "Scope probe",
                "planned_start_date": frappe.utils.today(),
            }
        )
        doc.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        return doc.name

    def _report(self, building):
        doc = frappe.get_doc(
            {
                "doctype": DOCTYPE,
                "naming_series": "MIR-.YYYY.-.####",
                "inspection_date": frappe.utils.today(),
                "building": building,
                "inspector": "Administrator",
                "findings": [
                    {"doctype": "Inspection Finding Item", "description": "probe"}
                ],
            }
        )
        doc.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        return doc.name

    def _pair(self):
        return self._report(self.b1), self._report(self.b2)

    def _rows_the_fragment_returns(self, user):
        """The names the desk list would return for ``user``.

        The fragment is exactly what `permission_query_conditions` AND-s into
        `DatabaseQuery`'s WHERE clause, and it is built from `frappe.db.escape`d
        values, so running it verbatim is the same read the list view performs.
        """
        fragment = P.building_scope_query(doctype=DOCTYPE, user=user)
        if fragment == "1=0":
            return set()
        where = " where {0}".format(fragment) if fragment else ""
        return set(
            frappe.db.sql_list(
                "select name from `tabMaintenance Inspection Report`" + where
            )
        )

    def test_the_scoped_list_keeps_this_estate_and_drops_the_other(self):
        mine, theirs = self._pair()
        names = self._rows_the_fragment_returns(self.scoped)
        self.assertIn(mine, names, "the supervisor lost their own estate")
        self.assertNotIn(theirs, names, "another estate's inspection leaked")

    def test_oversight_sees_both_estates(self):
        """The control that stops a deny-everything fragment from passing."""
        mine, theirs = self._pair()
        names = self._rows_the_fragment_returns(self.oversight)
        self.assertIn(mine, names)
        self.assertIn(theirs, names)

    def test_a_supervisor_with_no_building_permission_sees_nothing(self):
        """The hole the fragment exists to close: frappe's native match adds NO
        condition for a user holding no Building User Permission."""
        mine, theirs = self._pair()
        self.assertEqual(P.building_scope_query(doctype=DOCTYPE, user=self.unpermitted), "1=0")
        names = self._rows_the_fragment_returns(self.unpermitted)
        self.assertNotIn(mine, names)
        self.assertNotIn(theirs, names)

    def test_the_fragment_names_the_building_column_and_only_this_estate(self):
        fragment = P.building_scope_query(doctype=DOCTYPE, user=self.scoped)
        self.assertIn("`building`", fragment)
        self.assertIn(self.b1, fragment)
        self.assertNotIn(self.b2, fragment)
        self.assertEqual(P.building_scope_query(doctype=DOCTYPE, user=self.oversight), "")

    def test_the_controller_hook_opens_this_estate_and_denies_the_other(self):
        """Isolates the hook from frappe's native check, which would deny the same
        document on its own and so cannot prove the wiring."""
        mine, theirs = self._pair()
        self.assertIsNone(
            P.building_scoped_has_permission(
                frappe.get_doc(DOCTYPE, mine), "read", user=self.scoped
            )
        )
        self.assertIs(
            P.building_scoped_has_permission(
                frappe.get_doc(DOCTYPE, theirs), "read", user=self.scoped
            ),
            False,
        )

    def test_a_create_with_building_unfetched_is_decided_by_the_work_order(self):
        """The create path against real rows, both ways.

        `frappe.get_doc` applies no `fetch_from` -- that runs in `_validate_links()`
        during insert -- so `building` here is genuinely empty at the moment
        `check_permission("create")` would read it.
        """
        for building, expected in ((self.b1, None), (self.b2, False)):
            with self.subTest(building=building):
                draft = frappe.get_doc(
                    {
                        "doctype": DOCTYPE,
                        "naming_series": "MIR-.YYYY.-.####",
                        "inspection_date": frappe.utils.today(),
                        "inspector": "Administrator",
                        "maintenance_work_order": self._work_order(building),
                    }
                )
                self.assertFalse(draft.get("building"), "fetch_from ran too early")
                self.assertIs(
                    P.building_scoped_has_permission(draft, "create", user=self.scoped),
                    expected,
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)
