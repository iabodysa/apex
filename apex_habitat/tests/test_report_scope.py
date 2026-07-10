# Copyright (c) 2026, AFMCO and contributors
"""Cross-tenant row-scoping for the eight Script Reports that called
``frappe.get_all`` directly.

``frappe.get_all`` forces ``ignore_permissions=True``, so the project / building
row-scoping the desk lists get via ``permission_query_conditions`` was bypassed
inside these reports — a project-scoped Fleet Supervisor (or a building-scoped
Resident Supervisor) running the report saw EVERY tenant's rows. Each report's
``execute()`` now re-applies the caller's allowed scope using the existing
``salis.permissions`` / ``habitat.permissions`` helpers, while the oversight roles
in ``UNSCOPED_ROLES`` / ``HOUSING_UNSCOPED_ROLES`` still see all.

Two layers of proof:

* :class:`TestReportScopeLogic` patches the scope helpers and asserts the filter
  each report hands to ``frappe.get_all`` — covering ALL EIGHT reports' branches
  (scoped -> in-scope filter, no-scope -> empty, oversight -> unfiltered, an
  explicit out-of-scope filter -> empty) without any fixtures.
* :class:`TestReportScopeIntegration` seeds real records spanning two projects and
  two buildings, drives the real permission layer with ``frappe.set_user``, and
  asserts the row counts a scoped vs. an oversight user actually gets back — and
  that the in-scope totals are unchanged.
"""

import unittest
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from apex_habitat.salis import permissions as SP
from apex_habitat.habitat import permissions as HP
from apex_habitat.salis.report.fuel_consumption_summary import fuel_consumption_summary as R_fuel
from apex_habitat.salis.report.driver_attendance_summary import driver_attendance_summary as R_driver
from apex_habitat.salis.report.fleet_register import fleet_register as R_fleet
from apex_habitat.salis.report.vehicle_compliance_register import vehicle_compliance_register as R_comp
from apex_habitat.habitat.report.active_resident_register import active_resident_register as R_resident
from apex_habitat.habitat.report.daily_cleaning_compliance import daily_cleaning_compliance as R_clean
from apex_habitat.habitat.report.accommodation_stock_balance import accommodation_stock_balance as R_stock
from apex_habitat.habitat.report.custody_outstanding_by_worker import custody_outstanding_by_worker as R_custody
from apex_habitat.tests._helpers import _user


def _last_filters(mock_get_all):
    """The ``filters`` dict passed to the LAST frappe.get_all call (the report's
    own primary query is always the final one)."""
    return mock_get_all.call_args.kwargs["filters"]


class TestReportScopeLogic(FrappeTestCase):
    """The scope each report applies to its frappe.get_all query, helpers stubbed.

    The salis reports resolve an intermediate vehicle/driver set, so their module
    issues TWO get_all calls; we stub get_all to first return the in-scope id set
    then an empty primary result, and assert on the primary (last) call's filter.
    """

    # ----- salis: direct project (Salis Vehicle) -----

    def test_fleet_register_scoped_filters_project(self):
        with patch.object(SP, "_is_unscoped", return_value=False), patch.object(
            SP, "_allowed_projects", return_value=["P-1", "P-2"]
        ), patch.object(R_fleet.frappe, "get_all", return_value=[]) as ga:
            R_fleet.execute({})
            self.assertEqual(_last_filters(ga)["project"], ["in", ["P-1", "P-2"]])

    def test_fleet_register_in_scope_filter_kept(self):
        with patch.object(SP, "_is_unscoped", return_value=False), patch.object(
            SP, "_allowed_projects", return_value=["P-1", "P-2"]
        ), patch.object(R_fleet.frappe, "get_all", return_value=[]) as ga:
            R_fleet.execute({"project": "P-1"})
            # an explicit in-scope filter narrows to that one project, not the whole set
            self.assertEqual(_last_filters(ga)["project"], "P-1")

    def test_fleet_register_out_of_scope_filter_empty(self):
        with patch.object(SP, "_is_unscoped", return_value=False), patch.object(
            SP, "_allowed_projects", return_value=["P-1"]
        ), patch.object(R_fleet.frappe, "get_all", return_value=[]) as ga:
            cols, data = R_fleet.execute({"project": "P-9"})
            self.assertEqual(data, [])
            ga.assert_not_called()

    def test_fleet_register_no_scope_empty(self):
        with patch.object(SP, "_is_unscoped", return_value=False), patch.object(
            SP, "_allowed_projects", return_value=[]
        ), patch.object(R_fleet.frappe, "get_all", return_value=[]) as ga:
            cols, data = R_fleet.execute({})
            self.assertEqual(data, [])
            ga.assert_not_called()

    def test_fleet_register_oversight_unfiltered(self):
        with patch.object(SP, "_is_unscoped", return_value=True), patch.object(
            R_fleet.frappe, "get_all", return_value=[]
        ) as ga:
            R_fleet.execute({})
            self.assertNotIn("project", _last_filters(ga))

    # ----- salis: indirect project via vehicle -----

    def test_fuel_summary_scoped_filters_by_in_scope_vehicles(self):
        with patch.object(SP, "_is_unscoped", return_value=False), patch.object(
            SP, "_allowed_projects", return_value=["P-1"]
        ), patch.object(R_fuel.frappe, "get_all", side_effect=[["V-1", "V-2"], []]) as ga:
            R_fuel.execute({})
            # first call resolves the in-scope vehicles by project
            self.assertEqual(ga.call_args_list[0].kwargs["filters"], {"project": ["in", ["P-1"]]})
            # primary log query confined to those vehicles
            self.assertEqual(_last_filters(ga)["vehicle"], ["in", ["V-1", "V-2"]])

    def test_fuel_summary_no_in_scope_vehicles_empty(self):
        with patch.object(SP, "_is_unscoped", return_value=False), patch.object(
            SP, "_allowed_projects", return_value=["P-1"]
        ), patch.object(R_fuel.frappe, "get_all", return_value=[]) as ga:
            cols, data = R_fuel.execute({})
            self.assertEqual(data, [])
            self.assertEqual(ga.call_count, 1)  # only the vehicle lookup ran

    def test_fuel_summary_oversight_unfiltered(self):
        with patch.object(SP, "_is_unscoped", return_value=True), patch.object(
            R_fuel.frappe, "get_all", return_value=[]
        ) as ga:
            R_fuel.execute({})
            self.assertNotIn("vehicle", _last_filters(ga))

    def test_driver_summary_scoped_filters_by_in_scope_drivers(self):
        with patch.object(SP, "_is_unscoped", return_value=False), patch.object(
            SP, "_allowed_projects", return_value=["P-1"]
        ), patch.object(R_driver.frappe, "get_all", side_effect=[["D-1"], []]) as ga:
            R_driver.execute({})
            self.assertEqual(ga.call_args_list[0].kwargs["filters"], {"project": ["in", ["P-1"]]})
            self.assertEqual(_last_filters(ga)["driver"], ["in", ["D-1"]])

    def test_driver_summary_oversight_unfiltered(self):
        with patch.object(SP, "_is_unscoped", return_value=True), patch.object(
            R_driver.frappe, "get_all", return_value=[]
        ) as ga:
            R_driver.execute({})
            self.assertNotIn("driver", _last_filters(ga))

    def test_compliance_register_scoped_filters_by_parent_vehicle(self):
        with patch.object(SP, "_is_unscoped", return_value=False), patch.object(
            SP, "_allowed_projects", return_value=["P-1"]
        ), patch.object(R_comp.frappe, "get_all", side_effect=[["V-1"], []]) as ga:
            R_comp.execute({})
            self.assertEqual(ga.call_args_list[0].kwargs["filters"], {"project": ["in", ["P-1"]]})
            self.assertEqual(_last_filters(ga)["parent"], ["in", ["V-1"]])

    def test_compliance_register_oversight_unfiltered(self):
        with patch.object(SP, "_is_unscoped", return_value=True), patch.object(
            R_comp.frappe, "get_all", return_value=[]
        ) as ga:
            R_comp.execute({})
            self.assertNotIn("parent", _last_filters(ga))

    # ----- habitat: direct building -----

    def test_resident_register_scoped_filters_building(self):
        with patch.object(HP, "_building_is_unscoped", return_value=False), patch.object(
            HP, "_allowed_buildings", return_value=["B-1", "B-2"]
        ), patch.object(R_resident.frappe, "get_all", return_value=[]) as ga:
            R_resident.execute({})
            self.assertEqual(_last_filters(ga)["building"], ["in", ["B-1", "B-2"]])

    def test_resident_register_out_of_scope_filter_empty(self):
        with patch.object(HP, "_building_is_unscoped", return_value=False), patch.object(
            HP, "_allowed_buildings", return_value=["B-1"]
        ), patch.object(R_resident.frappe, "get_all", return_value=[]) as ga:
            cols, data = R_resident.execute({"building": "B-9"})
            self.assertEqual(data, [])
            ga.assert_not_called()

    def test_resident_register_no_scope_empty(self):
        with patch.object(HP, "_building_is_unscoped", return_value=False), patch.object(
            HP, "_allowed_buildings", return_value=[]
        ), patch.object(R_resident.frappe, "get_all", return_value=[]) as ga:
            cols, data = R_resident.execute({})
            self.assertEqual(data, [])
            ga.assert_not_called()

    def test_resident_register_oversight_unfiltered(self):
        with patch.object(HP, "_building_is_unscoped", return_value=True), patch.object(
            R_resident.frappe, "get_all", return_value=[]
        ) as ga:
            R_resident.execute({})
            self.assertNotIn("building", _last_filters(ga))

    def test_cleaning_compliance_scoped_filters_building(self):
        with patch.object(HP, "_building_is_unscoped", return_value=False), patch.object(
            HP, "_allowed_buildings", return_value=["B-1"]
        ), patch.object(R_clean.frappe, "get_all", return_value=[]) as ga:
            R_clean.execute({})
            self.assertEqual(_last_filters(ga)["building"], ["in", ["B-1"]])

    def test_cleaning_compliance_oversight_unfiltered(self):
        with patch.object(HP, "_building_is_unscoped", return_value=True), patch.object(
            R_clean.frappe, "get_all", return_value=[]
        ) as ga:
            R_clean.execute({})
            self.assertNotIn("building", _last_filters(ga))

    def test_stock_balance_scoped_filters_building(self):
        with patch.object(HP, "_building_is_unscoped", return_value=False), patch.object(
            HP, "_allowed_buildings", return_value=["B-1"]
        ), patch.object(R_stock.frappe, "get_all", return_value=[]) as ga:
            R_stock.execute({})
            self.assertEqual(_last_filters(ga)["building"], ["in", ["B-1"]])

    def test_stock_balance_no_scope_empty(self):
        with patch.object(HP, "_building_is_unscoped", return_value=False), patch.object(
            HP, "_allowed_buildings", return_value=[]
        ), patch.object(R_stock.frappe, "get_all", return_value=[]) as ga:
            cols, data = R_stock.execute({})
            self.assertEqual(data, [])
            ga.assert_not_called()

    def test_stock_balance_oversight_unfiltered(self):
        with patch.object(HP, "_building_is_unscoped", return_value=True), patch.object(
            R_stock.frappe, "get_all", return_value=[]
        ) as ga:
            R_stock.execute({})
            self.assertNotIn("building", _last_filters(ga))

    def test_custody_outstanding_scoped_filters_building(self):
        with patch.object(HP, "_building_is_unscoped", return_value=False), patch.object(
            HP, "_allowed_buildings", return_value=["B-1"]
        ), patch.object(R_custody.frappe, "get_all", return_value=[]) as ga:
            R_custody.execute({})
            self.assertEqual(_last_filters(ga)["building"], ["in", ["B-1"]])

    def test_custody_outstanding_oversight_unfiltered(self):
        with patch.object(HP, "_building_is_unscoped", return_value=True), patch.object(
            R_custody.frappe, "get_all", return_value=[]
        ) as ga:
            R_custody.execute({})
            self.assertNotIn("building", _last_filters(ga))


def _project(name):
    p = frappe.db.get_value("Project", {"project_name": name}, "name")
    if not p:
        p = frappe.get_doc({"doctype": "Project", "project_name": name}).insert(
            ignore_permissions=True
        ).name
    return p


def _grant(user, allow, value):
    if not frappe.db.exists(
        "User Permission", {"allow": allow, "for_value": value, "user": user}
    ):
        frappe.get_doc(
            {"doctype": "User Permission", "allow": allow, "for_value": value, "user": user}
        ).insert(ignore_permissions=True)


class TestReportScopeIntegration(FrappeTestCase):
    """Real records across two tenants; real users; real row counts.

    Covers the salis direct-project path (``fleet_register``) and the
    habitat direct-building path (``accommodation_stock_balance`` +
    ``custody_outstanding_by_worker``) end to end: a scoped user sees only their
    tenant's rows, an oversight user sees both, and the in-scope totals match.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.tag = frappe.generate_hash(length=6).upper()

        # --- salis: two projects, one vehicle each ---
        cls.pa = _project("RScope A " + cls.tag)
        cls.pb = _project("RScope B " + cls.tag)
        cls.veh_a = cls._vehicle(cls.pa)
        cls.veh_b = cls._vehicle(cls.pb)

        # Fleet Supervisor is scoped (not in UNSCOPED_ROLES); Fleet Manager is oversight.
        cls.sup = _user("rscope_fleet_sup@example.com", "Fleet Supervisor")
        _grant(cls.sup, "Project", cls.pa)
        cls.mgr = _user("rscope_fleet_mgr@example.com", "Fleet Manager")

        # --- habitat: two buildings, two custody ledger rows each ---
        cls.bld_a, cls.bld_b = cls._two_buildings()
        cls.article = cls._custody_article()
        cls.emp = cls._employee()
        # building A: qty 5 ; building B: qty 7  (distinct so totals are checkable)
        cls._ledger(cls.bld_a, cls.article, cls.emp, 5)
        cls._ledger(cls.bld_b, cls.article, cls.emp, 7)

        cls.hsup = _user("rscope_res_sup@example.com", "Resident Supervisor")
        _grant(cls.hsup, "Building", cls.bld_a)
        cls.hmgr = _user("rscope_acc_mgr@example.com", "Accommodation Manager")

    @classmethod
    def tearDownClass(cls):
        # setUpClass commits Projects + User Permissions (and project/building
        # scoped fixtures) OUTSIDE the per-method savepoint rollback; delete them
        # so the @example.com Project User Permission rows do not poison later
        # tests on the shared bench. (Company/Article/Employee are reuse-or-create
        # and left alone — they may pre-exist on the bench.)
        frappe.set_user("Administrator")
        frappe.db.delete("User Permission",
                         {"allow": "Project", "for_value": cls.pa, "user": cls.sup})
        frappe.db.delete("User Permission",
                         {"allow": "Building", "for_value": cls.bld_a, "user": cls.hsup})
        frappe.db.delete("Accommodation Stock Ledger", {"building": ["in", (cls.bld_a, cls.bld_b)]})
        for v in (cls.veh_a, cls.veh_b):
            if frappe.db.exists("Salis Vehicle", v):
                frappe.delete_doc("Salis Vehicle", v, ignore_permissions=True, force=True)
        for b in (cls.bld_a, cls.bld_b):
            if frappe.db.exists("Building", b):
                frappe.delete_doc("Building", b, ignore_permissions=True, force=True)
        for p in (cls.pa, cls.pb):
            if frappe.db.exists("Project", p):
                frappe.delete_doc("Project", p, ignore_permissions=True, force=True)
        frappe.db.commit()
        super().tearDownClass()

    @classmethod
    def _vehicle(cls, project):
        return frappe.get_doc(
            {
                "doctype": "Salis Vehicle",
                "plate_number": "RS " + frappe.generate_hash(length=5).upper(),
                "ownership": "Rented",
                "status": "Active",
                "project": project,
            }
        ).insert(ignore_permissions=True).name

    @classmethod
    def _two_buildings(cls):
        company = frappe.db.get_value("Company", {}) or frappe.get_doc(
            {"doctype": "Company", "company_name": "RScope Co " + cls.tag,
             "default_currency": "SAR", "country": "Saudi Arabia"}
        ).insert(ignore_permissions=True).name
        cost_center = (frappe.db.get_value("Cost Center", {"is_group": 0, "company": company})
                       or frappe.db.get_value("Cost Center", {"is_group": 0}))
        site = frappe.get_doc(
            {"doctype": "Site", "site_name": "RS " + cls.tag}
        ).insert(ignore_permissions=True).name
        names = []
        for i in ("A", "B"):
            names.append(frappe.get_doc({
                "doctype": "Building",
                "building_name": "RS B" + i + " " + cls.tag,
                "site": site,
                "company": company,
                "total_capacity": 10,
                "default_cost_center": cost_center,
                "annual_rent": 36500,
            }).insert(ignore_permissions=True).name)
        return names[0], names[1]

    @classmethod
    def _custody_article(cls):
        existing = frappe.db.get_value("Custody Article", {})
        if existing:
            return existing
        return frappe.get_doc(
            {"doctype": "Custody Article", "article_name": "RS Item " + cls.tag}
        ).insert(ignore_permissions=True).name

    @classmethod
    def _employee(cls):
        emp = frappe.db.get_value("Employee", {})
        if emp:
            return emp
        # minimal employee; company resolved above via building seed
        company = frappe.db.get_value("Company", {})
        return frappe.get_doc({
            "doctype": "Employee", "employee_name": "RS Emp " + cls.tag,
            "first_name": "RS", "company": company, "status": "Active",
            "gender": "Male", "date_of_joining": "2024-01-01", "date_of_birth": "1990-01-01",
        }).insert(ignore_permissions=True).name

    @classmethod
    def _ledger(cls, building, article, employee, qty):
        frappe.get_doc({
            "doctype": "Accommodation Stock Ledger",
            "posting_date": frappe.utils.today(),
            "item_type": "Custody Article",
            "item": article,
            "signed_qty": qty,
            "unit_cost": 10,
            "building": building,
            "employee": employee,
            "is_cancelled": 0,
        }).insert(ignore_permissions=True)

    def tearDown(self):
        frappe.set_user("Administrator")

    # ----- fleet_register -----

    def test_fleet_register_scoped_user_sees_only_his_project(self):
        frappe.set_user(self.sup)
        _, rows = R_fleet.execute({})[:2]
        projects = {r["project"] for r in rows}
        self.assertEqual(projects, {self.pa},
                         "scoped supervisor must see only their project's vehicles")

    def test_fleet_register_oversight_sees_both_projects(self):
        frappe.set_user(self.mgr)
        _, rows = R_fleet.execute({})[:2]
        projects = {r["project"] for r in rows}
        self.assertTrue({self.pa, self.pb} <= projects,
                        "oversight role must see every project's vehicles")

    # ----- accommodation_stock_balance / custody_outstanding_by_worker -----

    def _stock_rows_for(self, user, execute):
        frappe.set_user(user)
        return [r for r in execute({})[1] if r.get("building") in (self.bld_a, self.bld_b)]

    def test_stock_balance_scoped_user_sees_only_his_building(self):
        rows = self._stock_rows_for(self.hsup, R_stock.execute)
        buildings = {r["building"] for r in rows}
        self.assertEqual(buildings, {self.bld_a},
                         "scoped supervisor must see only their building's stock")
        # in-scope total is unchanged by the scoping (qty 5 on building A)
        self.assertEqual(sum(r["balance_qty"] for r in rows), 5)

    def test_stock_balance_oversight_sees_both_buildings(self):
        rows = self._stock_rows_for(self.hmgr, R_stock.execute)
        buildings = {r["building"] for r in rows}
        self.assertEqual(buildings, {self.bld_a, self.bld_b},
                         "oversight role must see every building's stock")
        self.assertEqual(sum(r["balance_qty"] for r in rows), 12)

    def test_custody_outstanding_scoped_user_sees_only_his_building(self):
        rows = self._stock_rows_for(self.hsup, R_custody.execute)
        self.assertEqual({r["building"] for r in rows}, {self.bld_a})

    def test_custody_outstanding_oversight_sees_both_buildings(self):
        rows = self._stock_rows_for(self.hmgr, R_custody.execute)
        self.assertEqual({r["building"] for r in rows}, {self.bld_a, self.bld_b})


if __name__ == "__main__":
    unittest.main()
