# Copyright (c) 2026, afmcoltd
"""The shared scoping primitives, driven through their three real consumers.

``apex.habitat.permissions`` (Building), ``apex.salis.permissions`` (Project) and
``apex.logistay.permissions`` (Company) all delegate to
``apex.apex_core.utils.permission_scope``. This file is the security oracle for that
arrangement: with REAL Users, REAL User Permissions and the REAL framework it asserts, for
four representative identities, that the three externally-observable outputs are exactly
what each module promises — the ``permission_query_conditions`` fragment, the
``report_*_scope`` tuple, and the ``has_permission`` verdict.

Nothing here builds an estate. ``test_dependencies = ["Building"]`` stands the whole chain
up once per run — Building pulls Site and ERPNext's ``_Test Company`` — and gives two
buildings, which is exactly the in-scope / out-of-scope pair these cases need. The previous
form of this file minted a Company, a Site and two Buildings in ``setUpClass`` and deleted
them again in ``tearDownClass``.

The identities and their User Permissions ARE the subject here, so they are still built.
They are class-scoped and uncommitted, so ``FrappeTestCase``'s class rollback removes them.

The expected fragment is rebuilt inline from the same ``frappe.db.escape`` + ``col in (...)``
recipe the primitive uses, so the assertion locks the SHAPE, not a hard-coded value.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.apex_core.utils import permission_scope
from apex.habitat import permissions as HP
from apex.logistay import permissions as LP
from apex.salis import permissions as SP
from apex.tests._helpers import _grant_project, _user

# Project is deliberately NOT a dependency. ERPNext's Project fixture is not idempotent —
# its autoname mints a new name while project_name carries a unique index, so a rebuild
# collides instead of being skipped. The scope only needs a project id, so the one already
# on the site is read rather than rebuilt.
test_dependencies = ["Building"]

BUILDING = "_Test Building"
BUILDING_OTHER = "_Test Building 2"

# Custody Issue and Fuel Quota are the plain-column representatives of their axes: both
# resolve through ``_column(...)`` with no own-row basis, so the fragment is the bare
# ``col in (...)`` the shared primitive emits and nothing module-specific is folded in.
HABITAT_DOCTYPE = "Custody Issue"
SALIS_DOCTYPE = "Fuel Quota"


def _grant(user, allow, for_value):
    if not frappe.db.exists(
        "User Permission", {"user": user, "allow": allow, "for_value": for_value}
    ):
        frappe.get_doc(
            {"doctype": "User Permission", "user": user, "allow": allow, "for_value": for_value}
        ).insert(ignore_permissions=True)


def _in(col, values):
    """Rebuild the exact `col in (...)` fragment the primitive emits."""
    return "{c} in ({v})".format(c=col, v=", ".join(frappe.db.escape(v) for v in values))


class TestSharedPermissionScope(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")

        cls.proj = frappe.db.get_value("Project", {"project_name": "_Test Project"})

        cls.bsup = _user("psc_res_sup@example.com", "Resident Supervisor")  # Building-scoped
        _grant(cls.bsup, "Building", BUILDING)
        cls.psup = _user("psc_fleet_sup@example.com", "Fleet Supervisor")  # Project-scoped
        _grant_project(cls.psup, cls.proj)
        cls.bmgr = _user("psc_acc_mgr@example.com", "Accommodation Manager")  # Building oversight
        cls.pmgr = _user("psc_fleet_mgr@example.com", "Fleet Manager")  # Project oversight
        # fully-unscoped: an ordinary user with no oversight role and no User Permission
        cls.bare = _user("psc_bare@example.com", "Fleet Supervisor")
        # dual: holds BOTH a Building and a Project permission (collision probe)
        cls.dual = _user("psc_dual@example.com", "Fleet Supervisor")
        _grant(cls.dual, "Building", BUILDING)
        _grant_project(cls.dual, cls.proj)

    def setUp(self):
        frappe.local.cache = {}
        self.addCleanup(frappe.set_user, "Administrator")

    def test_building_scoped_supervisor(self):
        self.assertEqual(
            HP.building_scope_query(user=self.bsup, doctype=HABITAT_DOCTYPE),
            _in("`building`", [BUILDING]),
        )
        self.assertEqual(
            HP.report_building_scope(user=self.bsup, doctype=HABITAT_DOCTYPE), (True, [BUILDING])
        )
        d_in = frappe._dict(doctype=HABITAT_DOCTYPE, building=BUILDING)
        d_out = frappe._dict(doctype=HABITAT_DOCTYPE, building=BUILDING_OTHER)
        self.assertIsNone(HP.building_scoped_has_permission(d_in, "read", user=self.bsup))
        self.assertFalse(HP.building_scoped_has_permission(d_out, "read", user=self.bsup))
        # submit is denied out-of-scope too (ptype-agnostic deny)
        self.assertFalse(HP.building_scoped_has_permission(d_out, "submit", user=self.bsup))

    def test_project_scoped_supervisor(self):
        self.assertEqual(
            SP.project_scope_query(user=self.psup, doctype=SALIS_DOCTYPE),
            _in("`project`", [self.proj]),
        )
        self.assertEqual(
            SP.report_project_scope(user=self.psup, doctype=SALIS_DOCTYPE), (True, [self.proj])
        )
        d_in = frappe._dict(doctype=SALIS_DOCTYPE, project=self.proj, owner="dispatcher")
        d_out = frappe._dict(doctype=SALIS_DOCTYPE, project="__none__", owner="dispatcher")
        self.assertIsNone(SP.project_scoped_has_permission(d_in, "read", user=self.psup))
        self.assertFalse(SP.project_scoped_has_permission(d_out, "read", user=self.psup))

    def test_building_oversight_role(self):
        self.assertEqual(HP.building_scope_query(user=self.bmgr, doctype=HABITAT_DOCTYPE), "")
        self.assertEqual(
            HP.report_building_scope(user=self.bmgr, doctype=HABITAT_DOCTYPE), (False, [])
        )
        d = frappe._dict(doctype=HABITAT_DOCTYPE, building=BUILDING_OTHER)
        self.assertIsNone(HP.building_scoped_has_permission(d, "read", user=self.bmgr))

    def test_project_oversight_role(self):
        self.assertEqual(SP.project_scope_query(user=self.pmgr, doctype=SALIS_DOCTYPE), "")
        self.assertEqual(
            SP.report_project_scope(user=self.pmgr, doctype=SALIS_DOCTYPE), (False, [])
        )
        d = frappe._dict(doctype=SALIS_DOCTYPE, project="anything", owner="x")
        self.assertIsNone(SP.project_scoped_has_permission(d, "read", user=self.pmgr))

    def test_fully_unscoped_bare_user(self):
        # Building side
        self.assertEqual(HP.building_scope_query(user=self.bare, doctype=HABITAT_DOCTYPE), "1=0")
        self.assertEqual(
            HP.report_building_scope(user=self.bare, doctype=HABITAT_DOCTYPE), (True, [])
        )
        b = frappe._dict(doctype=HABITAT_DOCTYPE, building=BUILDING)
        self.assertFalse(HP.building_scoped_has_permission(b, "read", user=self.bare))
        # Project side (bare holds Fleet Supervisor but no Project permission)
        self.assertEqual(SP.project_scope_query(user=self.bare, doctype=SALIS_DOCTYPE), "1=0")
        self.assertEqual(
            SP.report_project_scope(user=self.bare, doctype=SALIS_DOCTYPE), (True, [])
        )
        p = frappe._dict(doctype=SALIS_DOCTYPE, project=self.proj, owner="dispatcher")
        self.assertFalse(SP.project_scoped_has_permission(p, "read", user=self.bare))

    def test_dual_permission_no_cross_scope_collision(self):
        buildings = HP._allowed_buildings(self.dual)
        projects = SP._allowed_projects(self.dual)
        self.assertEqual(buildings, [BUILDING])
        self.assertEqual(projects, [self.proj])
        self.assertNotEqual(buildings, projects)
        # The two scopes are keyed by the `allow` doctype in frappe's own resolver, so a
        # Building scope can never be served where a Project scope was asked for.
        resolved = frappe.permissions.get_user_permissions(self.dual)
        self.assertEqual([row.get("doc") for row in resolved["Building"]], [BUILDING])
        self.assertEqual([row.get("doc") for row in resolved["Project"]], [self.proj])

    def test_wrappers_delegate_to_shared_module(self):
        # thin wrappers forward to the shared resolver
        self.assertEqual(HP._resolve_user("someone"), permission_scope.resolve_user("someone"))
        self.assertEqual(SP._resolve_user("someone"), permission_scope.resolve_user("someone"))
        self.assertEqual(LP._resolve_user("someone"), permission_scope.resolve_user("someone"))
        # is_unscoped honours the module-specific oversight set (never a shared default)
        self.assertTrue(permission_scope.is_unscoped("Administrator", HP.HOUSING_UNSCOPED_ROLES))
        self.assertFalse(permission_scope.is_unscoped("Guest", SP.UNSCOPED_ROLES))
        # each module keeps its OWN distinct oversight set
        self.assertIn("Accommodation Manager", HP.HOUSING_UNSCOPED_ROLES)
        self.assertNotIn("Accommodation Manager", SP.UNSCOPED_ROLES)
        self.assertIn("Fleet Manager", SP.UNSCOPED_ROLES)
        self.assertNotIn("Fleet Manager", HP.HOUSING_UNSCOPED_ROLES)
        self.assertNotIn("Fleet Manager", LP.UNSCOPED_ROLES)
