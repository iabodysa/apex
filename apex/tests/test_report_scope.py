# Copyright (c) 2026, AFMCO and contributors
"""Cross-tenant row-scoping for the Script Reports that call ``frappe.get_all``
directly.

``frappe.get_all`` forces ``ignore_permissions=True``, so the project / building
row-scoping the desk lists get via ``permission_query_conditions`` was bypassed
inside these reports — a project-scoped Fleet Supervisor (or a building-scoped
Resident Supervisor) running the report saw EVERY tenant's rows. Each report's
``execute()`` re-applies the caller's allowed scope using the existing
``salis.permissions`` / ``habitat.permissions`` helpers, while the oversight roles
in ``UNSCOPED_ROLES`` / ``HOUSING_UNSCOPED_ROLES`` still see all.

Three shipped reports carry that scoping: ``driver_attendance_summary`` and
``vehicle_compliance_register`` on the salis project axis, and
``accommodation_stock_balance`` on the habitat building axis.

Two layers of proof:

* :class:`TestReportScopeLogic` patches the scope helpers and asserts the filter
  each report hands to ``frappe.get_all`` — covering the branches (scoped ->
  in-scope filter, no-scope -> empty, oversight -> unfiltered) without fixtures.
* :class:`TestReportScopeIntegration` seeds real ledger rows spanning two
  buildings, drives the real permission layer with ``frappe.set_user``, and
  asserts the row counts a scoped vs. an oversight user actually gets back — and
  that the in-scope totals are unchanged.
"""

import unittest
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.salis import permissions as SP
from apex.habitat import permissions as HP
from apex.salis.report.driver_attendance_summary import driver_attendance_summary as R_driver
from apex.salis.report.vehicle_compliance_register import vehicle_compliance_register as R_comp
from apex.habitat.report.accommodation_stock_balance import accommodation_stock_balance as R_stock
from apex.tests._helpers import _user


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

    def test_driver_summary_scoped_filters_by_in_scope_drivers(self):
        """Driver Attendance is scoped project-OR-owner, so the driver list is an
        or_filter beside `owner = me` — matching driver_attendance_query's if_owner
        branch, which is why a project filter alone hid a Driver's own rows."""
        with patch.object(SP, "_is_unscoped", return_value=False), patch.object(
            SP, "_allowed_projects", return_value=["P-1"]
        ), patch.object(R_driver.frappe, "get_all", side_effect=[["D-1"], []]) as ga:
            R_driver.execute({})
            self.assertEqual(ga.call_args_list[0].kwargs["filters"], {"project": ["in", ["P-1"]]})
            or_filters = ga.call_args_list[-1].kwargs["or_filters"]
            self.assertEqual(or_filters["driver"], ["in", ["D-1"]])
            self.assertEqual(or_filters["owner"], frappe.session.user)

    def test_driver_summary_scoped_without_project_falls_back_to_own_rows(self):
        """A Driver holding no Project User Permission still sees the rows they own."""
        with patch.object(SP, "_is_unscoped", return_value=False), patch.object(
            SP, "_allowed_projects", return_value=[]
        ), patch.object(R_driver.frappe, "get_all", return_value=[]) as ga:
            R_driver.execute({})
            self.assertEqual(_last_filters(ga)["owner"], frappe.session.user)

    def test_driver_summary_oversight_unfiltered(self):
        """An oversight role gets no driver narrowing at all."""
        with patch.object(SP, "_is_unscoped", return_value=True), patch.object(
            R_driver.frappe, "get_all", return_value=[]
        ) as ga:
            R_driver.execute({})
            self.assertNotIn("driver", _last_filters(ga))

    def test_compliance_register_scoped_filters_by_parent_vehicle(self):
        """A scoped user's compliance rows are confined to their in-scope vehicles."""
        with patch.object(SP, "_is_unscoped", return_value=False), patch.object(
            SP, "_allowed_projects", return_value=["P-1"]
        ), patch.object(R_comp.frappe, "get_all", side_effect=[["V-1"], []]) as ga:
            R_comp.execute({})
            self.assertEqual(ga.call_args_list[0].kwargs["filters"], {"project": ["in", ["P-1"]]})
            self.assertEqual(_last_filters(ga)["parent"], ["in", ["V-1"]])

    def test_compliance_register_oversight_unfiltered(self):
        """An oversight role gets no parent-vehicle narrowing at all."""
        with patch.object(SP, "_is_unscoped", return_value=True), patch.object(
            R_comp.frappe, "get_all", return_value=[]
        ) as ga:
            R_comp.execute({})
            self.assertNotIn("parent", _last_filters(ga))

    def test_stock_balance_scoped_filters_building(self):
        """A building-scoped user's stock query carries an in-scope building filter."""
        with patch.object(HP, "_building_is_unscoped", return_value=False), patch.object(
            HP, "_allowed_buildings", return_value=["B-1"]
        ), patch.object(R_stock.frappe, "get_all", return_value=[]) as ga:
            R_stock.execute({})
            self.assertEqual(_last_filters(ga)["building"], ["in", ["B-1"]])

    def test_stock_balance_no_scope_empty(self):
        """A scoped user with no permitted building gets no rows and issues no query."""
        with patch.object(HP, "_building_is_unscoped", return_value=False), patch.object(
            HP, "_allowed_buildings", return_value=[]
        ), patch.object(R_stock.frappe, "get_all", return_value=[]) as ga:
            cols, data, *_rest = R_stock.execute({})
            self.assertEqual(data, [])
            ga.assert_not_called()

    def test_stock_balance_oversight_unfiltered(self):
        """An oversight role gets no building narrowing at all."""
        with patch.object(HP, "_building_is_unscoped", return_value=True), patch.object(
            R_stock.frappe, "get_all", return_value=[]
        ) as ga:
            R_stock.execute({})
            self.assertNotIn("building", _last_filters(ga))


def _grant(user, allow, value):
    """Give ``user`` a User Permission on ``value``, once."""
    if not frappe.db.exists(
        "User Permission", {"allow": allow, "for_value": value, "user": user}
    ):
        frappe.get_doc(
            {"doctype": "User Permission", "allow": allow, "for_value": value, "user": user}
        ).insert(ignore_permissions=True)


class TestReportScopeIntegration(FrappeTestCase):
    """Real records across two buildings; real users; real row counts.

    Covers the habitat direct-building path (``accommodation_stock_balance``) end
    to end: a scoped user sees only their tenant's rows, an oversight user sees
    both, and the in-scope totals match.
    """

    @classmethod
    def setUpClass(cls):
        """Seed two buildings, a custody article and one ledger row in each."""
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.tag = frappe.generate_hash(length=12).upper()

        cls.bld_a, cls.bld_b = cls._two_buildings()
        cls.article = cls._custody_article()
        cls.emp = cls._employee()
        cls._ledger(cls.bld_a, cls.article, cls.emp, 5)
        cls._ledger(cls.bld_b, cls.article, cls.emp, 7)

        cls.hsup = _user("rscope_res_sup@example.com", "Resident Supervisor")
        _grant(cls.hsup, "Building", cls.bld_a)
        cls.hmgr = _user("rscope_acc_mgr@example.com", "Accommodation Manager")

    @classmethod
    def tearDownClass(cls):
        """Drop the grant, the ledger rows and the buildings this class created."""
        frappe.set_user("Administrator")
        frappe.db.delete("User Permission",
                         {"allow": "Building", "for_value": cls.bld_a, "user": cls.hsup})
        frappe.db.delete("Accommodation Stock Ledger", {"building": ["in", (cls.bld_a, cls.bld_b)]})
        for b in (cls.bld_a, cls.bld_b):
            if frappe.db.exists("Building", b):
                frappe.delete_doc("Building", b, ignore_permissions=True, force=True)
        frappe.db.commit()
        super().tearDownClass()

    @classmethod
    def _two_buildings(cls):
        """Two Buildings on one Site, sharing whatever company and cost centre exist."""
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
        """Any existing Custody Article, else one created for this run."""
        existing = frappe.db.get_value("Custody Article", {})
        if existing:
            return existing
        return frappe.get_doc(
            {"doctype": "Custody Article", "article_name": "RS Item " + cls.tag}
        ).insert(ignore_permissions=True).name

    @classmethod
    def _employee(cls):
        """Any existing Employee, else one created for this run."""
        emp = frappe.db.get_value("Employee", {})
        if emp:
            return emp
        company = frappe.db.get_value("Company", {})
        return frappe.get_doc({
            "doctype": "Employee", "employee_name": "RS Emp " + cls.tag,
            "first_name": "RS", "company": company, "status": "Active",
            "gender": "Male", "date_of_joining": "2024-01-01", "date_of_birth": "1990-01-01",
        }).insert(ignore_permissions=True).name

    @classmethod
    def _ledger(cls, building, article, employee, qty):
        """One non-cancelled Accommodation Stock Ledger row in ``building``."""
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
        """Return to Administrator so the next test starts unscoped."""
        frappe.set_user("Administrator")

    def _stock_rows_for(self, user):
        """The stock balance rows ``user`` gets back, narrowed to this class's buildings."""
        frappe.set_user(user)
        return [r for r in R_stock.execute({})[1] if r.get("building") in (self.bld_a, self.bld_b)]

    def test_stock_balance_scoped_user_sees_only_his_building(self):
        """A building-scoped supervisor gets one building's rows and its total only."""
        rows = self._stock_rows_for(self.hsup)
        buildings = {r["building"] for r in rows}
        self.assertEqual(buildings, {self.bld_a},
                         "scoped supervisor must see only their building's stock")
        self.assertEqual(sum(r["balance_qty"] for r in rows), 5)

    def test_stock_balance_oversight_sees_both_buildings(self):
        """An oversight role gets both buildings' rows and the combined total."""
        rows = self._stock_rows_for(self.hmgr)
        buildings = {r["building"] for r in rows}
        self.assertEqual(buildings, {self.bld_a, self.bld_b},
                         "oversight role must see every building's stock")
        self.assertEqual(sum(r["balance_qty"] for r in rows), 12)


if __name__ == "__main__":
    unittest.main()
