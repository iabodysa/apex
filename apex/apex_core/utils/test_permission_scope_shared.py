# Copyright (c) 2026, AFMCO and contributors
"""Scoped-user regression for the shared permission-scope primitives (R5).

``apex.habitat.permissions`` (Building scope) and ``apex.salis.permissions``
(Project scope) now delegate five low-level primitives to
``apex.apex_core.utils.permission_scope`` — ``resolve_user``, ``allowed_for``,
``is_unscoped``, ``scope_condition``, ``report_scope`` — while keeping thin,
module-local wrappers that bind their own oversight-role set, ``allow`` doctype,
and cache namespace.

This test is the security oracle for that refactor: with REAL Users, REAL User
Permissions, and the REAL framework it asserts, for four representative identities
(a Building-scoped supervisor, a Project-scoped supervisor, an unscoped oversight
role, and a fully-unscoped bare user), that the three externally-observable
outputs of the scoping layer are EXACTLY what the pre-refactor algorithm produced:

  1. the ``permission_query_conditions`` SQL fragment (list/report visibility),
  2. the ``report_*_scope`` tuple (report-side re-scoping),
  3. the ``has_permission`` verdict (form / REST / link visibility).

The expected fragment is rebuilt inline from the same ``frappe.db.escape`` +
``col in (...)`` recipe the primitive uses, so the assertion is independent of the
(dynamic) tenant name — it locks the SHAPE, not a hard-coded value.

It also pins the security-critical invariant of primitive #2: a user holding BOTH
a Building AND a Project User Permission gets two DIFFERENT allowed sets from two
DISTINCT ``frappe.local.cache`` namespaces — a shared cache key here would be a
cross-scope data leak.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.apex_core.utils import permission_scope
from apex.habitat import permissions as HP
from apex.salis import permissions as SP
from apex.tests._helpers import _user, _project, _grant_project


def _grant_building(user, building):
    if not frappe.db.exists(
        "User Permission", {"user": user, "allow": "Building", "for_value": building}
    ):
        frappe.get_doc(
            {"doctype": "User Permission", "user": user,
             "allow": "Building", "for_value": building}
        ).insert(ignore_permissions=True)


def _in(col, values):
    """Rebuild the exact `col in (...)` fragment the primitive emits."""
    return "{c} in ({v})".format(
        c=col, v=", ".join(frappe.db.escape(v) for v in values)
    )


class TestSharedPermissionScope(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.tag = frappe.generate_hash(length=12).upper()

        # tenants
        cls.proj = _project("PScope " + cls.tag)
        cls.bld, cls.bld_other = cls._two_buildings()

        # identities
        cls.bsup = _user("psc_res_sup@example.com", "Resident Supervisor")   # Building-scoped
        _grant_building(cls.bsup, cls.bld)
        cls.psup = _user("psc_fleet_sup@example.com", "Fleet Supervisor")     # Project-scoped
        _grant_project(cls.psup, cls.proj)
        cls.bmgr = _user("psc_acc_mgr@example.com", "Accommodation Manager")  # Building oversight
        cls.pmgr = _user("psc_fleet_mgr@example.com", "Fleet Manager")        # Project oversight
        # fully-unscoped: an ordinary user with no oversight role and no User Permission
        cls.bare = _user("psc_bare@example.com", "Fleet Supervisor")
        # dual: holds BOTH a Building and a Project permission (collision probe)
        cls.dual = _user("psc_dual@example.com", "Fleet Supervisor")
        _grant_building(cls.dual, cls.bld)
        _grant_project(cls.dual, cls.proj)

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        for u in (cls.bsup, cls.dual):
            frappe.db.delete("User Permission",
                             {"allow": "Building", "for_value": cls.bld, "user": u})
        for u in (cls.psup, cls.dual):
            frappe.db.delete("User Permission",
                             {"allow": "Project", "for_value": cls.proj, "user": u})
        for b in (cls.bld, cls.bld_other):
            if frappe.db.exists("Building", b):
                frappe.delete_doc("Building", b, ignore_permissions=True, force=True)
        if frappe.db.exists("Project", cls.proj):
            frappe.delete_doc("Project", cls.proj, ignore_permissions=True, force=True)
        frappe.db.commit()
        super().tearDownClass()

    @classmethod
    def _two_buildings(cls):
        company = frappe.db.get_value("Company", {}) or frappe.get_doc(
            {"doctype": "Company", "company_name": "PSc Co " + cls.tag,
             "default_currency": "SAR", "country": "Saudi Arabia"}
        ).insert(ignore_permissions=True).name
        cost_center = (frappe.db.get_value("Cost Center", {"is_group": 0, "company": company})
                       or frappe.db.get_value("Cost Center", {"is_group": 0}))
        site = frappe.get_doc(
            {"doctype": "Site", "site_name": "PSc " + cls.tag}
        ).insert(ignore_permissions=True).name
        out = []
        for i in ("A", "B"):
            out.append(frappe.get_doc({
                "doctype": "Building", "building_name": "PSc B" + i + " " + cls.tag,
                "site": site, "company": company, "total_capacity": 10,
                "default_cost_center": cost_center, "annual_rent": 36500,
            }).insert(ignore_permissions=True).name)
        return out[0], out[1]

    def setUp(self):
        frappe.local.cache = {}

    def tearDown(self):
        frappe.set_user("Administrator")
        frappe.local.cache = {}

    # Building-scoped doctype (representative: Custody Issue)
    def test_building_scoped_supervisor(self):
        # 1) pqc fragment == `building` in (<my building>)
        self.assertEqual(
            HP.accommodation_assignment_query(user=self.bsup),
            _in("`building`", [self.bld]),
        )
        # 2) report tuple
        self.assertEqual(HP.report_building_scope(user=self.bsup), (True, [self.bld]))
        # 3) has_permission verdict: in-scope -> None (defer/allow), out -> False
        d_in = frappe._dict(doctype="Custody Issue", building=self.bld)
        d_out = frappe._dict(doctype="Custody Issue", building=self.bld_other)
        self.assertIsNone(HP.building_scoped_has_permission(d_in, "read", user=self.bsup))
        self.assertFalse(HP.building_scoped_has_permission(d_out, "read", user=self.bsup))
        # submit is denied out-of-scope too (ptype-agnostic deny)
        self.assertFalse(HP.building_scoped_has_permission(d_out, "submit", user=self.bsup))

    # Project-scoped doctype (representative: Fuel Request)
    def test_project_scoped_supervisor(self):
        self.assertEqual(
            SP.fuel_request_query(user=self.psup),
            _in("`project`", [self.proj]),
        )
        self.assertEqual(SP.report_project_scope(user=self.psup), (True, [self.proj]))
        d_in = frappe._dict(doctype="Fuel Request", project=self.proj, owner="dispatcher")
        d_out = frappe._dict(doctype="Fuel Request", project="__none__", owner="dispatcher")
        self.assertIsNone(SP.scoped_has_permission(d_in, "read", user=self.psup))
        self.assertFalse(SP.scoped_has_permission(d_out, "read", user=self.psup))

    # unscoped oversight roles: no restriction, always defer
    def test_building_oversight_role(self):
        self.assertEqual(HP.accommodation_assignment_query(user=self.bmgr), "")
        self.assertEqual(HP.report_building_scope(user=self.bmgr), (False, []))
        d = frappe._dict(doctype="Custody Issue", building=self.bld_other)
        self.assertIsNone(HP.building_scoped_has_permission(d, "read", user=self.bmgr))

    def test_project_oversight_role(self):
        self.assertEqual(SP.fuel_request_query(user=self.pmgr), "")
        self.assertEqual(SP.report_project_scope(user=self.pmgr), (False, []))
        d = frappe._dict(doctype="Fuel Request", project="anything", owner="x")
        self.assertIsNone(SP.scoped_has_permission(d, "read", user=self.pmgr))

    # ---- fully-unscoped bare user: scoped, no permission -> sees nothing - #
    def test_fully_unscoped_bare_user(self):
        # Building side
        self.assertEqual(HP.accommodation_assignment_query(user=self.bare), "1=0")
        self.assertEqual(HP.report_building_scope(user=self.bare), (True, []))
        b = frappe._dict(doctype="Custody Issue", building=self.bld)
        self.assertFalse(HP.building_scoped_has_permission(b, "read", user=self.bare))
        # Project side (bare holds Fleet Supervisor but no Project permission)
        self.assertEqual(SP.fuel_request_query(user=self.bare), "1=0")
        self.assertEqual(SP.report_project_scope(user=self.bare), (True, []))
        p = frappe._dict(doctype="Fuel Request", project=self.proj, owner="dispatcher")
        self.assertFalse(SP.scoped_has_permission(p, "read", user=self.bare))

    # ---- primitive #2 invariant: no Building<->Project cache collision --- #
    def test_dual_permission_no_cross_scope_collision(self):
        frappe.set_user(self.dual)
        buildings = HP._allowed_buildings(self.dual)
        projects = SP._allowed_projects(self.dual)
        self.assertEqual(buildings, [self.bld])
        self.assertEqual(projects, [self.proj])
        self.assertNotEqual(buildings, projects)
        # the two scopes live under DISTINCT local_cache namespaces
        self.assertIn("apex_allowed_buildings", frappe.local.cache)
        self.assertIn("apex_allowed_projects", frappe.local.cache)
        self.assertEqual(frappe.local.cache["apex_allowed_buildings"][self.dual], [self.bld])
        self.assertEqual(frappe.local.cache["apex_allowed_projects"][self.dual], [self.proj])

    # ---- the shared primitives are actually the ones being exercised ---- #
    def test_wrappers_delegate_to_shared_module(self):
        # thin wrappers forward to the shared resolver
        self.assertEqual(HP._resolve_user("someone"), permission_scope.resolve_user("someone"))
        self.assertEqual(SP._resolve_user("someone"), permission_scope.resolve_user("someone"))
        # is_unscoped honours the module-specific oversight set (never a shared default)
        self.assertTrue(permission_scope.is_unscoped("Administrator", HP.HOUSING_UNSCOPED_ROLES))
        self.assertFalse(permission_scope.is_unscoped("Guest", SP.UNSCOPED_ROLES))
        # each module keeps its OWN distinct oversight set
        self.assertIn("Accommodation Manager", HP.HOUSING_UNSCOPED_ROLES)
        self.assertNotIn("Accommodation Manager", SP.UNSCOPED_ROLES)
        self.assertIn("Fleet Manager", SP.UNSCOPED_ROLES)
        self.assertNotIn("Fleet Manager", HP.HOUSING_UNSCOPED_ROLES)
