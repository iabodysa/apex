# Copyright (c) 2026, AFMCO and contributors
"""Building row-scoping for Audit Remediation Plan through its child scope.

The plan carries NO `building` column. The estate it touches is the SET of buildings
listed in its `buildings_in_scope` child table, so neither the shared column fragment
nor the single-link hop serves it: the fragment is a subquery on
`tabAudit Remediation Building Scope` keyed on `parent`, the shape
`housing_checkout_query` uses for its bed hop widened from one link to a row set.

WHAT WAS LEAKING, precisely. Because the plan has no Building Link of its own,
frappe's native User Permission match (`DatabaseQuery.add_user_permissions`,
frappe/model/db_query.py:1079) emits NOTHING for this DocType -- it only matches
parent-level Link fields, never a child table's. So a Building User Permission alone
left every plan in every estate visible, and this fragment is the ONLY row scope
there is here, not a tightening of a native one.

WHY THE SHARED HANDLER COULD NOT BE REUSED. `building_scoped_has_permission` reads
`doc.building`, which this DocType does not have, so it would resolve None for every
plan and return False -- denying a scoped supervisor their OWN plans. That blackout
shape reviews as correct and is not, which is why the handler is its own function and
why every denial below is paired with a same-estate positive.

WHY NO CREATE-PATH ANCHOR IS OWED. Child rows arrive with the payload and are built in
`Document.__init__`, so unlike a `fetch_from` field the scope table IS
populated when `check_permission("create")` runs at frappe/model/document.py:300.
A test below asserts exactly that, so the claim is checked rather than assumed.

SHIPPED PERMISSIONS, HONESTLY. As of this commit the DocType's DocPerm rows are System
Manager, Accommodation Manager and Internal Auditor -- all three of which
`HOUSING_UNSCOPED_ROLES` treats as building oversight, so at runtime today no user
reaches the scoped branch. The wiring is therefore latent: correct the moment any
building-scoped role is granted read. Nothing here asserts that DocPerm set, because a
test that reds when someone correctly grants such a role would be a false alarm.

WHY `frappe.db.sql` AND NOT `frappe.get_list` IN THE RUNTIME CLASS. `get_all` forces
`ignore_permissions` (frappe/__init__.py:2050) so it proves nothing about scoping, and
`get_list` as a scoped user would raise PermissionError on a DocType they hold no
DocPerm for -- an empty result that would satisfy a "the other estate is not returned"
assertion for entirely the wrong reason. Running the fragment the hook injects against
the real rows is the same WHERE clause the desk list builds, and mutates no site
permission to observe it.
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

DOCTYPE = "Audit Remediation Plan"
CHILD_DOCTYPE = "Audit Remediation Building Scope"
CHILD_FIELD = "buildings_in_scope"
QUERY_FN = "apex.habitat.permissions.building_scope_query"
HANDLER = "apex.habitat.permissions.building_scoped_has_permission"

BLD_A = "ARP-BLD-A"
BLD_B = "ARP-BLD-B"


def _h(n=12):
    return frappe.generate_hash(length=n).upper()


def _plan(*buildings):
    """A doc-shaped stand-in whose child scope names ``buildings``."""
    return SimpleNamespace(
        doctype=DOCTYPE,
        **{CHILD_FIELD: [SimpleNamespace(building=b) for b in buildings]},
    )


def _scoped_to(buildings):
    return (
        patch.object(P, "_building_is_unscoped", return_value=False),
        patch.object(P, "_allowed_buildings", return_value=list(buildings)),
    )


class TestAuditRemediationPlanScopeWiring(unittest.TestCase):
    """Siteless: the two hook entries, the child-table premise, and the verdicts."""

    APEX = Path(apex.__file__).parent

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from apex import hooks

        cls.hooks = hooks
        cls.json = {}
        for slug in ("audit_remediation_plan", "audit_remediation_building_scope"):
            path = cls.APEX / "habitat" / "doctype" / slug / (slug + ".json")
            data = json.loads(path.read_text())
            cls.json[data["name"]] = data

    def test_the_list_view_is_wired_to_the_child_scope_fragment(self):
        self.assertEqual(
            self.hooks.permission_query_conditions.get(DOCTYPE),
            QUERY_FN,
            "the plan list has no building scope",
        )

    def test_the_form_and_rest_paths_are_wired_to_the_dedicated_handler(self):
        self.assertEqual(
            self.hooks.has_permission.get(DOCTYPE),
            HANDLER,
            "an out-of-estate plan is still openable",
        )

    def test_both_wired_targets_resolve_to_a_callable(self):
        for dotted in (QUERY_FN, HANDLER):
            with self.subTest(dotted=dotted):
                self.assertTrue(callable(getattr(P, dotted.rsplit(".", 1)[1])))

    def test_the_plan_really_has_no_building_column_of_its_own(self):
        """The premise of the card. If a `building` field is ever added, the shared
        column fragment becomes the right answer and this says so."""
        fieldnames = {f.get("fieldname") for f in self.json[DOCTYPE]["fields"]}
        self.assertNotIn("building", fieldnames)
        self.assertNotIn(DOCTYPE, P.BUILDING_FETCH_ANCHOR)

    def test_the_scope_table_the_subquery_reads_is_the_one_the_plan_declares(self):
        """A rename on either side would leave the subquery matching nothing --
        silently blacking out every scoped user rather than leaking, but still wrong."""
        table = next(
            f
            for f in self.json[DOCTYPE]["fields"]
            if f.get("fieldname") == CHILD_FIELD
        )
        self.assertEqual(table.get("fieldtype"), "Table")
        self.assertEqual(table.get("options"), CHILD_DOCTYPE)
        child = self.json[CHILD_DOCTYPE]
        self.assertEqual(child.get("istable"), 1)
        building = next(
            f for f in child["fields"] if f.get("fieldname") == "building"
        )
        self.assertEqual(building.get("options"), "Building")
        self.assertEqual(building.get("reqd"), 1)

    def test_the_handler_defers_in_estate_and_denies_out_of_estate(self):
        """Paired both ways: a handler that denied everything would pass half of this."""
        outer, inner = _scoped_to([BLD_A])
        with outer, inner:
            self.assertIsNone(
                P.building_scoped_has_permission(_plan(BLD_A), "read", user="sup"),
                "a supervisor was denied a plan naming their own building",
            )
            self.assertIs(
                P.building_scoped_has_permission(_plan(BLD_B), "read", user="sup"),
                False,
                "a plan naming only another estate was readable",
            )

    def test_a_plan_naming_several_buildings_is_visible_if_any_one_is_mine(self):
        """The set semantics the subquery has: a shared plan reaches every estate on it."""
        outer, inner = _scoped_to([BLD_A])
        with outer, inner:
            self.assertIsNone(
                P.building_scoped_has_permission(
                    _plan(BLD_B, BLD_A), "read", user="sup"
                )
            )

    def test_a_plan_naming_no_building_at_all_fails_closed(self):
        outer, inner = _scoped_to([BLD_A])
        with outer, inner:
            self.assertIs(
                P.building_scoped_has_permission(_plan(), "read", user="sup"),
                False,
            )
            self.assertIs(
                P.building_scoped_has_permission(
                    SimpleNamespace(doctype=DOCTYPE), "read", user="sup"
                ),
                False,
                "a plan with no scope table at all must be denied, not deferred",
            )

    def test_every_action_is_denied_out_of_estate_not_only_read(self):
        outer, inner = _scoped_to([BLD_A])
        with outer, inner:
            for ptype in ("read", "write", "create", "submit", "cancel", "delete"):
                with self.subTest(ptype=ptype):
                    self.assertIs(
                        P.building_scoped_has_permission(
                            _plan(BLD_B), ptype, user="sup"
                        ),
                        False,
                    )

    def test_oversight_defers_and_a_permissionless_scoped_user_is_denied(self):
        with patch.object(P, "_building_is_unscoped", return_value=True):
            self.assertIsNone(
                P.building_scoped_has_permission(_plan(BLD_B), "read", user="mgr")
            )
        outer, inner = _scoped_to([])
        with outer, inner:
            self.assertIs(
                P.building_scoped_has_permission(_plan(BLD_A), "read", user="sup"),
                False,
            )

    def test_the_fragment_renders_the_two_edge_cases_the_siblings_render(self):
        with patch.object(P, "_building_is_unscoped", return_value=True):
            self.assertEqual(P.building_scope_query(doctype=DOCTYPE, user="mgr"), "")
        outer, inner = _scoped_to([])
        with outer, inner:
            self.assertEqual(P.building_scope_query(doctype=DOCTYPE, user="sup"), "1=0")

    def test_the_fragment_subqueries_the_child_table_and_escapes_its_values(self):
        """The injection shape this must never take: an apostrophe in a building name
        has to arrive escaped, not spliced."""
        outer, inner = _scoped_to(["O'Hare Camp"])
        with outer, inner, patch.object(
            frappe, "db", SimpleNamespace(escape=lambda v: "'{0}'".format(v.replace("'", "\\'")))
        ):
            fragment = P.building_scope_query(doctype=DOCTYPE, user="sup")
        self.assertIn("`tabAudit Remediation Building Scope`", fragment)
        self.assertIn("select `parent`", fragment)
        self.assertIn("`parenttype` = 'Audit Remediation Plan'", fragment)
        self.assertIn("O\\'Hare Camp", fragment)


class TestAuditRemediationPlanScopeRuntime(FrappeTestCase):
    """Needs a bench site: real buildings, real child rows, a real User Permission."""

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
        doc = frappe.get_doc({"doctype": "Building", "building_name": "ARP-" + _h()})
        doc.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        cls.addClassCleanup(
            frappe.delete_doc, "Building", doc.name, force=True, ignore_permissions=True
        )
        return doc.name

    @classmethod
    def _user(cls, role):
        email = "arp-{0}@example.com".format(_h()).lower()
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

    def _payload(self, *buildings):
        return {
            "doctype": DOCTYPE,
            "naming_series": "CARP-.YYYY.-.####",
            "client_project": "ARP-SCOPE-PROBE",
            "audit_received_date": frappe.utils.today(),
            "remediation_deadline": frappe.utils.today(),
            CHILD_FIELD: [{"building": b} for b in buildings],
        }

    def _plan(self, *buildings):
        doc = frappe.get_doc(self._payload(*buildings))
        doc.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        return doc.name

    def _pair(self):
        return self._plan(self.b1), self._plan(self.b2)

    def _rows_the_fragment_returns(self, user):
        """The names the desk list would return for ``user``.

        The fragment is exactly what `permission_query_conditions` AND-s into
        `DatabaseQuery`'s WHERE clause, built from `frappe.db.escape`d values, so
        running it verbatim is the same read the list view performs.
        """
        fragment = P.building_scope_query(doctype=DOCTYPE, user=user)
        if fragment == "1=0":
            return set()
        where = " where {0}".format(fragment) if fragment else ""
        return set(
            frappe.db.sql_list("select name from `tabAudit Remediation Plan`" + where)
        )

    def test_the_scoped_list_keeps_a_plan_naming_this_estate_and_drops_the_other(self):
        mine, theirs = self._pair()
        names = self._rows_the_fragment_returns(self.scoped)
        self.assertIn(mine, names, "the supervisor lost a plan naming their building")
        self.assertNotIn(theirs, names, "a plan naming only another estate leaked")

    def test_a_plan_naming_both_estates_reaches_the_scoped_supervisor(self):
        shared = self._plan(self.b1, self.b2)
        self.assertIn(shared, self._rows_the_fragment_returns(self.scoped))

    def test_a_plan_naming_no_building_is_hidden_from_scope_and_kept_by_oversight(self):
        """Fail closed, and prove it is the SCOPE hiding it rather than the row missing."""
        empty = self._plan()
        self.assertNotIn(empty, self._rows_the_fragment_returns(self.scoped))
        self.assertIn(empty, self._rows_the_fragment_returns(self.oversight))

    def test_oversight_sees_both_estates(self):
        """The control that stops a deny-everything fragment from passing."""
        mine, theirs = self._pair()
        names = self._rows_the_fragment_returns(self.oversight)
        self.assertIn(mine, names)
        self.assertIn(theirs, names)

    def test_a_supervisor_with_no_building_permission_sees_nothing(self):
        mine, theirs = self._pair()
        self.assertEqual(P.building_scope_query(doctype=DOCTYPE, user=self.unpermitted), "1=0")
        names = self._rows_the_fragment_returns(self.unpermitted)
        self.assertNotIn(mine, names)
        self.assertNotIn(theirs, names)

    def test_the_fragment_names_only_this_estate(self):
        fragment = P.building_scope_query(doctype=DOCTYPE, user=self.scoped)
        self.assertIn(self.b1, fragment)
        self.assertNotIn(self.b2, fragment)
        self.assertEqual(P.building_scope_query(doctype=DOCTYPE, user=self.oversight), "")

    def test_the_controller_hook_opens_this_estate_and_denies_the_other(self):
        """Isolates the hook from frappe's native check, which cannot see a child
        table at all and so would deny neither."""
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

    def test_the_scope_table_is_already_populated_at_the_create_check(self):
        """Why this DocType owes no BUILDING_FETCH_ANCHOR entry, checked rather than
        assumed: an unsaved doc built from a payload already carries its child rows,
        so the create verdict is decided on the real scope both ways."""
        for building, expected in ((self.b1, None), (self.b2, False)):
            with self.subTest(building=building):
                draft = frappe.get_doc(self._payload(building))
                self.assertEqual(
                    [row.building for row in draft.get(CHILD_FIELD)], [building]
                )
                self.assertIs(
                    P.building_scoped_has_permission(
                        draft, "create", user=self.scoped
                    ),
                    expected,
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)
