# Copyright (c) 2026, AFMCO and contributors
"""Building row-scoping for the four remaining safety/cleaning DocTypes.

Safety Incident, Safety Inspection Report, Safety Finding Ledger and Cleaning
Compliance Ledger each carry a `building` Link, but until now neither hook dict in
`apex.hooks` mentioned them, unlike their siblings Safety Round, Safety Task
Execution and Cleaning Log.

WHAT WAS ACTUALLY LEAKING. A Building User Permission alone does narrow most of
this natively: `DatabaseQuery.add_user_permissions` (frappe/model/db_query.py:1079)
emits a match condition for every Link whose target has user permissions. Two holes
survive it, and the wiring closes both.

  * A scoped user holding NO Building User Permission at all gets NO native match
    condition and therefore sees every estate. `_building_condition` returns "1=0"
    for exactly that user. This is the decisive case and it has its own test below.
  * With `apply_strict_user_permissions` off (the default) the native fragment is
    `ifnull(building,'')='' or building in (...)` (db_query.py:1090), so a row whose
    building is empty stays visible. The two ledgers write `building` read-only from
    their engines rather than through a `reqd` field, so an empty one is reachable.

WHY `frappe.get_list` AND NOT `frappe.get_all`. `get_all` sets
`kwargs["ignore_permissions"] = True` (frappe/__init__.py:2050), so it never reaches
`permission_query_conditions` at all. A list assertion written with `get_all` proves
nothing about scoping; every list assertion here goes through `get_list`.

The class-level wiring guards need no site and are the ones that fail if any of the
eight hook entries is removed. The runtime class needs a bench site.
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
from apex.tests._helpers import as_user
from apex.tests.factories import make_scoped_supervisor

HANDLER = "apex.habitat.permissions.building_scoped_has_permission"

# doctype -> the permission_query_conditions target it must be wired to.
SCOPED = {
    "Safety Incident": "apex.habitat.permissions.safety_incident_query",
    "Safety Inspection Report": "apex.habitat.permissions.safety_inspection_report_query",
    "Safety Finding Ledger": "apex.habitat.permissions.safety_finding_ledger_query",
    "Cleaning Compliance Ledger": "apex.habitat.permissions.cleaning_compliance_ledger_query",
}

# The roles that actually hold read on these four and are NOT building-oversight.
# Safety Finding Ledger grants no row to Resident Supervisor, Cleaning Compliance
# Ledger none either, so one user needs all three to exercise all four DocTypes.
SCOPED_ROLES = ("Resident Supervisor", "Safety Officer", "Cleaning Supervisor")

BLD_A = "SCS-BLD-A"
BLD_B = "SCS-BLD-B"


def _h(n=12):
    return frappe.generate_hash(length=n).upper()


class TestSafetyCleaningScopeWiring(unittest.TestCase):
    """Siteless: the eight hook entries, their targets, and the column they name."""

    APEX = Path(apex.__file__).parent

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from apex import hooks

        cls.hooks = hooks
        cls.json = {}
        for path in (cls.APEX / "habitat" / "doctype").glob("*/*.json"):
            try:
                data = json.loads(path.read_text())
            except ValueError:
                continue
            if data.get("doctype") == "DocType" and data.get("name") in SCOPED:
                cls.json[data["name"]] = data

    def test_each_doctype_has_a_permission_query_condition(self):
        for doctype, target in SCOPED.items():
            with self.subTest(doctype=doctype):
                self.assertEqual(
                    self.hooks.permission_query_conditions.get(doctype),
                    target,
                    "{0} has no list-view building scope".format(doctype),
                )

    def test_each_doctype_has_a_has_permission_entry(self):
        for doctype in SCOPED:
            with self.subTest(doctype=doctype):
                self.assertEqual(
                    self.hooks.has_permission.get(doctype),
                    HANDLER,
                    "{0} has no form/REST building scope".format(doctype),
                )

    def test_every_wired_target_resolves_to_a_callable(self):
        """A typo in a dotted path fails here, not on a customer site."""
        for doctype, target in SCOPED.items():
            with self.subTest(doctype=doctype):
                self.assertTrue(callable(getattr(P, target.rsplit(".", 1)[1])))
        self.assertTrue(callable(getattr(P, HANDLER.rsplit(".", 1)[1])))

    def test_each_doctype_carries_the_building_column_the_fragment_names(self):
        """The blackout shape: the fragment and the handler both read `building`.

        A wired DocType without that column would deny a scoped supervisor their OWN
        estate, which reviews as correct and is not.
        """
        for doctype in SCOPED:
            with self.subTest(doctype=doctype):
                data = self.json.get(doctype)
                self.assertIsNotNone(data, "{0}: DocType JSON not found".format(doctype))
                field = next(
                    (f for f in data["fields"] if f.get("fieldname") == "building"), None
                )
                self.assertIsNotNone(field, "{0}: no building field".format(doctype))
                self.assertEqual(field.get("options"), "Building")
                # Not fetched from a parent, so `building` is already in the payload at
                # the create check and no BUILDING_FETCH_ANCHOR entry is owed.
                self.assertFalse(
                    field.get("fetch_from"),
                    "{0}: a fetched building needs a create-path anchor".format(doctype),
                )
                self.assertNotIn(doctype, P.BUILDING_FETCH_ANCHOR)

    def test_building_is_the_only_building_link_so_no_link_is_over_restricted(self):
        """Why none of the four needs ``ignore_user_permissions``.

        A Building User Permission auto-filters EVERY Link whose target is Building
        (db_query.py:1083). That is wanted on the scope axis and silently
        over-restricts on any other Building link. Each of the four has exactly one.
        """
        for doctype in SCOPED:
            with self.subTest(doctype=doctype):
                building_links = [
                    f["fieldname"]
                    for f in self.json[doctype]["fields"]
                    if f.get("fieldtype") == "Link" and f.get("options") == "Building"
                ]
                self.assertEqual(building_links, ["building"])

    def test_the_handler_defers_in_estate_and_denies_out_of_estate(self):
        """Paired both ways: a handler that denied everything would pass half of this."""
        with patch.object(P, "_building_is_unscoped", return_value=False), patch.object(
            P, "_allowed_buildings", return_value=[BLD_A]
        ):
            for doctype in SCOPED:
                with self.subTest(doctype=doctype):
                    inside = SimpleNamespace(doctype=doctype, building=BLD_A)
                    outside = SimpleNamespace(doctype=doctype, building=BLD_B)
                    nowhere = SimpleNamespace(doctype=doctype, building=None)
                    self.assertIsNone(
                        P.building_scoped_has_permission(inside, "read", user="sup"),
                        "{0}: a supervisor was denied their own estate".format(doctype),
                    )
                    self.assertIs(
                        P.building_scoped_has_permission(outside, "read", user="sup"),
                        False,
                        "{0}: another estate's record was readable".format(doctype),
                    )
                    self.assertIs(
                        P.building_scoped_has_permission(nowhere, "read", user="sup"),
                        False,
                        "{0}: an unresolvable estate must fail closed".format(doctype),
                    )

    def test_every_action_is_denied_out_of_estate_not_only_read(self):
        with patch.object(P, "_building_is_unscoped", return_value=False), patch.object(
            P, "_allowed_buildings", return_value=[BLD_A]
        ):
            for ptype in ("read", "write", "create", "submit", "cancel", "delete"):
                with self.subTest(ptype=ptype):
                    self.assertIs(
                        P.building_scoped_has_permission(
                            SimpleNamespace(doctype="Safety Incident", building=BLD_B),
                            ptype,
                            user="sup",
                        ),
                        False,
                    )

    def test_oversight_defers_everywhere(self):
        with patch.object(P, "_building_is_unscoped", return_value=True):
            for doctype in SCOPED:
                with self.subTest(doctype=doctype):
                    self.assertIsNone(
                        P.building_scoped_has_permission(
                            SimpleNamespace(doctype=doctype, building=BLD_B),
                            "read",
                            user="mgr",
                        )
                    )

    def test_none_of_the_scoped_roles_is_a_building_oversight_role(self):
        """The trap: if any of these were oversight, every runtime denial below
        would be vacuous because the user would be unrestricted by design."""
        for role in SCOPED_ROLES:
            with self.subTest(role=role):
                self.assertNotIn(role, P.HOUSING_UNSCOPED_ROLES)


class TestSafetyCleaningScopeRuntime(FrappeTestCase):
    """Needs a bench site: real buildings, a real User Permission, real list reads."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.b1 = cls._building()
        cls.b2 = cls._building()
        # Scoped to b1 only, and holding every role that reads the four.
        cls.scoped = make_scoped_supervisor(cls._user, cls.b1, cls.addClassCleanup)
        frappe.get_doc("User", cls.scoped).add_roles(*SCOPED_ROLES[1:])
        # Same roles, NO Building User Permission — the user frappe's native match
        # leaves completely unrestricted.
        cls.unpermitted = cls._user(SCOPED_ROLES[0])
        frappe.get_doc("User", cls.unpermitted).add_roles(*SCOPED_ROLES[1:])
        cls.oversight = cls._user("Accommodation Manager")

    @classmethod
    def _building(cls):
        doc = frappe.get_doc({"doctype": "Building", "building_name": "SCS-" + _h()})
        doc.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        cls.addClassCleanup(
            frappe.delete_doc, "Building", doc.name, force=True, ignore_permissions=True
        )
        return doc.name

    @classmethod
    def _user(cls, role):
        email = "scs-{0}@example.com".format(_h()).lower()
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

    def _record(self, doctype, building):
        """One minimal record of ``doctype`` in ``building``; returns its name.

        No delete cleanup on purpose: both ledgers refuse ``on_trash`` by design, and
        FrappeTestCase's per-test rollback removes plain rows anyway.
        """
        payload = {"doctype": doctype, "building": building}
        if doctype == "Safety Incident":
            payload.update(
                {
                    "incident_datetime": frappe.utils.now_datetime(),
                    "severity": "Low",
                    "description": "Scope probe",
                }
            )
        elif doctype == "Safety Inspection Report":
            payload.update(
                {"inspection_date": frappe.utils.today(), "inspector": "Administrator"}
            )
        doc = frappe.get_doc(payload)
        doc.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        return doc.name

    @staticmethod
    def _list_names(doctype, user):
        with as_user(user):
            return {
                r.name
                for r in frappe.get_list(doctype, fields=["name"], limit_page_length=0)
            }

    def _pair(self, doctype):
        return self._record(doctype, self.b1), self._record(doctype, self.b2)

    def test_scoped_supervisor_list_excludes_the_other_estate(self):
        for doctype in SCOPED:
            with self.subTest(doctype=doctype):
                mine, theirs = self._pair(doctype)
                names = self._list_names(doctype, self.scoped)
                self.assertIn(
                    mine, names, "{0}: supervisor lost their own estate".format(doctype)
                )
                self.assertNotIn(
                    theirs, names, "{0}: another estate leaked".format(doctype)
                )

    def test_oversight_sees_both_estates(self):
        """The control that stops a deny-everything fragment from passing."""
        for doctype in SCOPED:
            with self.subTest(doctype=doctype):
                mine, theirs = self._pair(doctype)
                names = self._list_names(doctype, self.oversight)
                self.assertIn(mine, names)
                self.assertIn(theirs, names)

    def test_a_supervisor_with_no_building_permission_sees_nothing(self):
        """The hole the hooks exist to close.

        Frappe's native match adds NO condition for a user with no Building User
        Permission, so before the wiring this user read every estate. The fragment
        renders "1=0" instead.
        """
        for doctype in SCOPED:
            with self.subTest(doctype=doctype):
                mine, theirs = self._pair(doctype)
                names = self._list_names(doctype, self.unpermitted)
                self.assertNotIn(mine, names)
                self.assertNotIn(theirs, names)

    def test_form_access_is_allowed_in_estate_and_denied_out_of_estate(self):
        for doctype in SCOPED:
            with self.subTest(doctype=doctype):
                mine, theirs = self._pair(doctype)
                inside = frappe.get_doc(doctype, mine)
                outside = frappe.get_doc(doctype, theirs)
                self.assertTrue(
                    frappe.has_permission(doctype, "read", doc=inside, user=self.scoped),
                    "{0}: supervisor cannot open their own record".format(doctype),
                )
                self.assertFalse(
                    frappe.has_permission(doctype, "read", doc=outside, user=self.scoped),
                    "{0}: another estate's record was openable".format(doctype),
                )

    def test_the_controller_hook_itself_is_what_denies_the_other_estate(self):
        """Isolates the hook from frappe's native User Permission check, which would
        deny the same document on its own and so cannot prove the wiring."""
        for doctype in SCOPED:
            with self.subTest(doctype=doctype):
                mine, theirs = self._pair(doctype)
                self.assertIsNone(
                    P.building_scoped_has_permission(
                        frappe.get_doc(doctype, mine), "read", user=self.scoped
                    )
                )
                self.assertIs(
                    P.building_scoped_has_permission(
                        frappe.get_doc(doctype, theirs), "read", user=self.scoped
                    ),
                    False,
                )

    def test_the_fragment_names_the_building_column_and_only_the_users_estate(self):
        for doctype, target in SCOPED.items():
            with self.subTest(doctype=doctype):
                frag = getattr(P, target.rsplit(".", 1)[1])(user=self.scoped)
                self.assertIn("`building`", frag)
                self.assertIn(self.b1, frag)
                self.assertNotIn(self.b2, frag)
                self.assertEqual(
                    getattr(P, target.rsplit(".", 1)[1])(user=self.oversight), ""
                )
                self.assertEqual(
                    getattr(P, target.rsplit(".", 1)[1])(user=self.unpermitted), "1=0"
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)
