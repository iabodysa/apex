# Copyright (c) 2026, AFMCO and contributors
"""Site-backed integration tests for the Habitat role/permission alignment pass.

This module proves the alignment end-to-end against a live test site, complementing
the pure-structural guards in test_setup_roles.py / test_internal_auditor_docperms.py
/ test_habitat_permission_hooks.py:

  1. Idempotency (runtime) — after seeding, each of the four NEW operational roles
     and four NEW Role Profiles exists exactly once; re-running create_roles() /
     create_role_profiles() inserts no duplicates and does not raise.

  2. Maintenance Request owner isolation (T4) — a user holding ONLY 'Maintenance
     Technician' (no Habitat manager role) CAN raise a Maintenance Request, and its
     owner == reported_by == that user; that user CANNOT read a ticket owned by
     someone else (the query returns an owner/assigned_to fragment and
     has_permission returns False for a non-owned doc); a privileged role gets ''
     from the query and None from has_permission (full-visibility regression guard);
     assigned_to == user also grants visibility.

  3. Internal Auditor read-only — on the live DocType meta, Internal Auditor has
     read+report and NOT write/create/delete/submit/cancel across the
     custody/asset/movement/ledger set.

The owner-isolation tests drive the permission hooks directly (importing
maintenance_request_query / maintenance_request_has_permission), exactly as
test_salis_scoping.py imports scoped_has_permission.
"""

import unittest

import frappe
from frappe.tests.utils import FrappeTestCase

from apex_habitat.habitat.permissions import (
    maintenance_request_has_permission,
    maintenance_request_query,
)
from apex_habitat.setup import create_role_profiles, create_roles
from apex_habitat.tests._helpers import _user

# [#9o4st8]
NEW_ROLES = [
    "Maintenance Technician",
    "Cleaning Supervisor",
    "Safety Officer",
    "Resident Request Coordinator",
]

# [#1v581y]
NEW_PROFILES = [
    "Habitat Maintenance Technician",
    "Habitat Cleaning Supervisor",
    "Habitat Safety Officer",
    "Habitat Resident Request Coordinator",
]

# [#8rltpv]
PRIVILEGED_ROLES = [
    "Accommodation Manager",
    "Resident Supervisor",
    "Resident Request Coordinator",
    "System Manager",
]

# [#9g0uai]
AUDITOR_DOCTYPES = [
    "Custody Issue",
    "Custody Return",
    "Custody Damage Assessment",
    "Facility Asset",
    "Facility Asset Movement",
    "Facility Asset Custody Assignment",
    "Accommodation Ledger",
]

_WRITE_RIGHTS = ("write", "create", "delete", "submit", "cancel", "amend")


class TestRoleProfileIdempotency(FrappeTestCase):
    """create_roles() / create_role_profiles() are create-only: count stays 1."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        # [#l0z8d5]
        create_roles()
        create_role_profiles()
        frappe.db.commit()

    def test_each_new_role_exists_exactly_once(self):
        for role in NEW_ROLES:
            self.assertEqual(
                frappe.db.count("Role", {"name": role}),
                1,
                f"Role {role!r} must exist exactly once",
            )

    def test_each_new_profile_exists_exactly_once(self):
        for profile in NEW_PROFILES:
            self.assertEqual(
                frappe.db.count("Role Profile", {"name": profile}),
                1,
                f"Role Profile {profile!r} must exist exactly once",
            )

    def test_reseeding_creates_no_duplicates_and_does_not_raise(self):
        before_roles = {r: frappe.db.count("Role", {"name": r}) for r in NEW_ROLES}
        before_profiles = {
            p: frappe.db.count("Role Profile", {"name": p}) for p in NEW_PROFILES
        }
        # [#74ju57]
        create_roles()
        create_role_profiles()
        for role, count in before_roles.items():
            self.assertEqual(count, 1)
            self.assertEqual(frappe.db.count("Role", {"name": role}), 1)
        for profile, count in before_profiles.items():
            self.assertEqual(count, 1)
            self.assertEqual(frappe.db.count("Role Profile", {"name": profile}), 1)

    def test_each_new_profile_bundles_exactly_its_one_role(self):
        expected = {
            "Habitat Maintenance Technician": "Maintenance Technician",
            "Habitat Cleaning Supervisor": "Cleaning Supervisor",
            "Habitat Safety Officer": "Safety Officer",
            "Habitat Resident Request Coordinator": "Resident Request Coordinator",
        }
        for profile, role in expected.items():
            # [#4y41c3]
            roles = [r.role for r in frappe.get_doc("Role Profile", profile).roles]
            self.assertEqual(
                roles, [role], f"{profile!r} must bundle exactly [{role!r}]"
            )


class TestMaintenanceRequestOwnerIsolation(FrappeTestCase):
    """Universal intake, private tickets: a technician-only user can raise a
    ticket and see only their own; privileged roles see everything."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        create_roles()
        # [#fizkrr]
        cls.tech = _user("mra_tech@example.com", "Maintenance Technician")
        # [#3flk8c]
        cls.other = _user("mra_other@example.com", "Maintenance Technician")
        # [#rdgulg]
        cls.privileged = {
            role: _user(
                "mra_{}@example.com".format(role.replace(" ", "_").lower()), role
            )
            for role in PRIVILEGED_ROLES
        }
        frappe.db.commit()

    def tearDown(self):
        frappe.set_user("Administrator")

    def _doc(self, owner=None, assigned_to=None):
        """A lightweight stand-in for a Maintenance Request row, matching the
        shape the has_permission hook inspects (owner / assigned_to)."""
        return frappe._dict(
            {
                "doctype": "Maintenance Request",
                "owner": owner,
                "assigned_to": assigned_to,
            }
        )

    # [#72ccnr]

    def test_technician_can_raise_and_owns_the_request(self):
        frappe.set_user(self.tech)
        try:
            doc = frappe.get_doc(
                {
                    "doctype": "Maintenance Request",
                    "naming_series": "MAINT-.YYYY.-.#####",
                    "building": "QA-BLDG",
                    "room": "ROOM-QA",
                    "issue_type": "Plumbing",
                    "issue_description": "Tap dripping in shared bathroom",
                }
            )
            # [#8yri7d]
            doc.insert(ignore_links=True)
            name = doc.name
        finally:
            frappe.set_user("Administrator")
        try:
            # [#2klbw0]
            self.assertEqual(doc.reported_by, self.tech)
            self.assertEqual(doc.owner, self.tech)
            self.assertEqual(doc.owner, doc.reported_by)
        finally:
            frappe.delete_doc(
                "Maintenance Request", name, force=True, ignore_permissions=True
            )

    # [#asyc98]

    def test_technician_query_is_owner_scoped(self):
        frag = maintenance_request_query(user=self.tech)
        escaped = frappe.db.escape(self.tech)
        self.assertEqual(
            frag, "(`owner` = {0} or `assigned_to` = {0})".format(escaped)
        )

    def test_technician_cannot_read_a_non_owned_request(self):
        # [#kpc5xu]
        self.assertFalse(
            maintenance_request_has_permission(
                self._doc(owner=self.other), "read", user=self.tech
            )
        )

    def test_technician_can_read_own_request(self):
        self.assertTrue(
            maintenance_request_has_permission(
                self._doc(owner=self.tech), "read", user=self.tech
            )
        )

    def test_assignee_can_read_assigned_request(self):
        # [#gmkrru]
        self.assertTrue(
            maintenance_request_has_permission(
                self._doc(owner=self.other, assigned_to=self.tech),
                "read",
                user=self.tech,
            )
        )

    # [#cjncnb]

    def test_privileged_roles_have_no_query_restriction(self):
        for role, user in self.privileged.items():
            self.assertEqual(
                maintenance_request_query(user=user),
                "",
                f"{role!r} must get an unrestricted ('') query fragment",
            )

    def test_privileged_roles_defer_on_has_permission(self):
        for role, user in self.privileged.items():
            self.assertIsNone(
                maintenance_request_has_permission(
                    self._doc(owner=self.other), "read", user=user
                ),
                f"{role!r} must defer (None) to its own DocPerms",
            )


class TestInternalAuditorReadOnly(FrappeTestCase):
    """Internal Auditor: read+report only across custody/asset/movement/ledger."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        create_roles()
        frappe.db.commit()

    def _auditor_perm(self, doctype):
        meta = frappe.get_meta(doctype)
        rows = [p for p in meta.permissions if p.role == "Internal Auditor"]
        self.assertEqual(
            len(rows),
            1,
            f"{doctype}: expected exactly one Internal Auditor perm row, got {len(rows)}",
        )
        return rows[0]

    def test_auditor_has_read_and_report_everywhere(self):
        for doctype in AUDITOR_DOCTYPES:
            perm = self._auditor_perm(doctype)
            self.assertEqual(perm.read, 1, f"{doctype}: auditor must have read")
            self.assertEqual(perm.report, 1, f"{doctype}: auditor must have report")

    def test_auditor_has_no_write_rights_anywhere(self):
        for doctype in AUDITOR_DOCTYPES:
            perm = self._auditor_perm(doctype)
            for right in _WRITE_RIGHTS:
                self.assertNotEqual(
                    getattr(perm, right, 0),
                    1,
                    f"{doctype}: Internal Auditor must NOT have {right}",
                )

    def test_auditor_read_resolves_via_role_permissions(self):
        # [#1rjvse]
        from frappe.permissions import get_role_permissions

        original = frappe.session.user
        for doctype in AUDITOR_DOCTYPES:
            frappe.set_user("Administrator")
            auditor = _user("mra_auditor@example.com", "Internal Auditor")
            frappe.set_user(auditor)
            try:
                perms = get_role_permissions(frappe.get_meta(doctype), user=auditor)
                self.assertTrue(perms.get("read"), f"{doctype}: auditor read denied")
                for right in _WRITE_RIGHTS:
                    self.assertFalse(
                        perms.get(right),
                        f"{doctype}: auditor unexpectedly granted {right}",
                    )
            finally:
                frappe.set_user(original)


if __name__ == "__main__":
    unittest.main()
