# Copyright (c) 2026, AFMCO and contributors
"""Building (tenant) row-scoping for the Habitat DocTypes.

A Resident Supervisor holding a User Permission on ONE Accommodation Building must:
  * get a NON-empty permission_query_conditions fragment for every scoped DocType,
  * have that fragment EXCLUDE another building's rows from the List view,
  * be DENIED (has_permission False) on an out-of-building doc — including submit,
while an oversight role (Accommodation Manager) stays unrestricted (empty fragment,
defer-to-default has_permission). Occupancy Snapshot history is additionally
delete-locked to System Manager.

The pqc/has_permission functions are pure given a (user, doc), so most assertions
drive them directly with synthetic buildings + lightweight frappe._dict docs — no
per-DocType mandatory-field wrangling. One end-to-end List-view test inserts real
rows for a single-building and a dual-building DocType to prove the fragment filters.
"""

from functools import partial

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.habitat import permissions as P
from apex.tests._helpers import as_user
from apex.tests.factories import make_scoped_supervisor


def _scoped(doctype):
    """Drive the hook the way frappe drives it: one dispatcher, doctype passed in.

    ``db_query.py:1129`` calls the registered target as
    ``frappe.call(target, user, doctype=self.doctype)``, so binding the doctype here
    exercises the same entry point the List view uses rather than a name only a test
    knows.
    """
    return partial(P.building_scope_query, doctype=doctype)


SINGLE_BUILDING = [
    ("Facility Asset Custody Assignment", _scoped("Facility Asset Custody Assignment")),
    ("Operational Depreciation Snapshot", _scoped("Operational Depreciation Snapshot")),
    ("Custody Return", _scoped("Custody Return")),
    ("Custody Damage Assessment", _scoped("Custody Damage Assessment")),
    ("Custody Acknowledgment", _scoped("Custody Acknowledgment")),
    ("Facility Asset", _scoped("Facility Asset")),
    ("Housing Inventory", _scoped("Housing Inventory")),
    ("Building License", _scoped("Building License")),
    ("Maintenance Work Order", _scoped("Maintenance Work Order")),
    ("Occupancy Snapshot", _scoped("Occupancy Snapshot")),
    ("Temporary Worker", _scoped("Temporary Worker")),
    ("Arrival Batch", _scoped("Arrival Batch")),
    ("Room", _scoped("Room")),
    ("Bed", _scoped("Bed")),
    ("Accommodation Stock Ledger", _scoped("Accommodation Stock Ledger")),
]

DUAL_BUILDING = [
    ("Material Transfer", _scoped("Material Transfer")),
    ("Facility Asset Movement", _scoped("Facility Asset Movement")),
    ("Custody Handover", _scoped("Custody Handover")),
]


def _h(n=12):
    return frappe.generate_hash(length=n).upper()


class TestHabitatTenantScope(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.b1 = cls._building()
        cls.b2 = cls._building()
        cls.scoped = make_scoped_supervisor(cls._user, cls.b1, cls.addClassCleanup)
        cls.oversight = cls._oversight_manager()

    @classmethod
    def _building(cls):
        doc = frappe.get_doc({"doctype": "Building", "building_name": "TEN-" + _h()})
        doc.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        cls.addClassCleanup(
            frappe.delete_doc, "Building", doc.name, force=True, ignore_permissions=True
        )
        return doc.name

    @classmethod
    def _user(cls, role):
        email = "tenant-{0}@example.com".format(_h()).lower()
        u = frappe.get_doc({
            "doctype": "User",
            "email": email,
            "first_name": "Tenant",
            "send_welcome_email": 0,
            "roles": [{"role": role}],
        })
        u.insert(ignore_permissions=True)
        cls.addClassCleanup(frappe.delete_doc, "User", email, force=True, ignore_permissions=True)
        return email

    @classmethod
    def _oversight_manager(cls):
        return cls._user("Accommodation Manager")

    def test_single_building_pqc_non_empty_and_bounded(self):
        for dt, fn in SINGLE_BUILDING:
            frag = fn(user=self.scoped)
            self.assertTrue(frag, "{0}: scoped supervisor must get a non-empty pqc".format(dt))
            self.assertIn("`building`", frag, "{0}: fragment must constrain the building column".format(dt))
            self.assertIn(self.b1, frag, "{0}: fragment must include the user's building".format(dt))
            self.assertNotIn(self.b2, frag, "{0}: fragment must NOT include other buildings".format(dt))

    def test_dual_building_pqc_non_empty_and_bounded(self):
        for dt, fn in DUAL_BUILDING:
            frag = fn(user=self.scoped)
            self.assertTrue(frag, "{0}: scoped supervisor must get a non-empty pqc".format(dt))
            self.assertIn("`from_building`", frag, "{0}: must scope from_building".format(dt))
            self.assertIn("`to_building`", frag, "{0}: must scope to_building".format(dt))
            self.assertIn(self.b1, frag)

    def test_oversight_pqc_is_empty(self):
        for dt, fn in SINGLE_BUILDING + DUAL_BUILDING:
            self.assertEqual(fn(user=self.oversight), "", "{0}: oversight role must be unrestricted".format(dt))

    def test_single_building_has_permission_denies_other_estate(self):
        in_scope = frappe.get_doc({"doctype": "Facility Asset", "building": self.b1})
        out_scope = frappe.get_doc({"doctype": "Facility Asset", "building": self.b2})
        self.assertIsNone(
            P.building_scoped_has_permission(in_scope, "read", user=self.scoped),
            "in-building doc must defer to default (not be denied)",
        )
        self.assertIs(
            P.building_scoped_has_permission(out_scope, "read", user=self.scoped),
            False,
            "out-of-building doc must be denied",
        )

    def test_single_building_cross_estate_submit_denied(self):
        out_scope = frappe.get_doc({"doctype": "Facility Asset Custody Assignment", "building": self.b2})
        self.assertIs(
            P.building_scoped_has_permission(out_scope, "submit", user=self.scoped),
            False,
            "cross-building submit must be denied",
        )

    def test_dual_building_has_permission_matches_either_endpoint(self):
        from_ok = frappe._dict(doctype="Material Transfer", from_building=self.b1, to_building=self.b2)
        to_ok = frappe._dict(doctype="Material Transfer", from_building=self.b2, to_building=self.b1)
        neither = frappe._dict(doctype="Material Transfer", from_building=self.b2, to_building=self.b2)
        self.assertIsNone(P.building_scoped_has_permission(from_ok, "read", user=self.scoped))
        self.assertIsNone(P.building_scoped_has_permission(to_ok, "read", user=self.scoped))
        self.assertIs(P.building_scoped_has_permission(neither, "read", user=self.scoped), False)

    def test_dual_building_cross_estate_submit_denied(self):
        neither = frappe._dict(doctype="Facility Asset Movement", from_building=self.b2, to_building=self.b2)
        self.assertIs(
            P.building_scoped_has_permission(neither, "submit", user=self.scoped),
            False,
            "a transfer between two other estates must not be submittable by a scoped user",
        )

    def test_oversight_has_permission_defers(self):
        out_single = frappe.get_doc({"doctype": "Facility Asset", "building": self.b2})
        out_dual = frappe._dict(doctype="Facility Asset Movement", from_building=self.b2, to_building=self.b2)
        self.assertIsNone(P.building_scoped_has_permission(out_single, "read", user=self.oversight))
        self.assertIsNone(P.building_scoped_has_permission(out_dual, "read", user=self.oversight))

    def test_scoped_user_with_no_building_sees_nothing(self):
        lonely = self._user("Resident Supervisor")
        self.assertEqual(_scoped("Facility Asset")(user=lonely), "1=0")
        self.assertEqual(_scoped("Material Transfer")(user=lonely), "1=0")

    def test_list_view_excludes_other_building_single(self):
        a = self._asset(self.b1)
        b = self._asset(self.b2)
        names = self._list_names("Facility Asset", self.scoped)
        self.assertIn(a, names, "scoped supervisor sees their own building's asset")
        self.assertNotIn(b, names, "scoped supervisor must NOT see another building's asset")
        names_all = self._list_names("Facility Asset", self.oversight)
        self.assertIn(a, names_all)
        self.assertIn(b, names_all)

    def test_list_view_dual_building_matches_either_endpoint(self):
        touching = self._transfer(self.b2, self.b1)
        outside = self._transfer(self.b2, self.b2)
        names = self._list_names("Material Transfer", self.scoped)
        self.assertIn(touching, names, "a transfer touching the user's estate is visible")
        self.assertNotIn(outside, names, "a transfer between two other estates is hidden")

    def _asset(self, building):
        doc = frappe.get_doc({"doctype": "Facility Asset", "building": building})
        doc.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        self.addCleanup(frappe.delete_doc, "Facility Asset", doc.name, force=True, ignore_permissions=True)
        return doc.name

    def _transfer(self, from_b, to_b):
        doc = frappe.get_doc({
            "doctype": "Material Transfer",
            "from_building": from_b,
            "to_building": to_b,
        })
        doc.flags.ignore_validate = True
        doc.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        self.addCleanup(
            frappe.delete_doc, "Material Transfer", doc.name, force=True, ignore_permissions=True
        )
        return doc.name

    @staticmethod
    def _list_names(doctype, user):
        with as_user(user):
            return {r.name for r in frappe.get_list(doctype, fields=["name"], limit_page_length=0)}

    def test_occupancy_snapshot_delete_locked_to_system_manager(self):
        perms = frappe.get_meta("Occupancy Snapshot").permissions
        deleters = {p.role for p in perms if p.delete}
        self.assertEqual(
            deleters,
            {"System Manager"},
            "only System Manager may delete system-generated occupancy history",
        )
        for role in ("Accommodation Manager", "Resident Supervisor", "Finance Manager"):
            row = next(p for p in perms if p.role == role)
            self.assertTrue(row.read, "{0} keeps read".format(role))
            self.assertFalse(row.delete, "{0} must not delete history".format(role))


