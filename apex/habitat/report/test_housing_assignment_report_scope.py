# Copyright (c) 2026, AFMCO and contributors
"""The three Housing Assignment reports must scope through ONE seam.

``frappe.get_all`` forces ``ignore_permissions=True`` (frappe/__init__.py:2050), so the
building row-scoping the desk list gets from ``accommodation_assignment_query`` via
``permission_query_conditions`` is bypassed inside a Script Report. Every report over a
scoped DocType therefore has to re-apply the boundary in Python, and the question this
file settles is WHERE it gets the boundary from.

Two of the three reports used to resolve it themselves, calling
``permissions._building_is_unscoped`` and ``permissions._allowed_buildings`` and
re-deriving the verdict inline. That is equivalent to the seam only by coincidence of
duplication: it produces the same answer today and silently stops tracking the seam the
moment the seam changes shape — the ``bed``-hop ``housing_checkout_query`` already needs
is exactly such a change. Prose cannot detect that drift, which is why the check below
is a test.

WHY PATCHING THE SEAM IS THE DRIFT DETECTOR
:class:`TestHousingAssignmentReportsRouteThroughTheSeam` patches
``permissions.report_building_scope`` — the SEAM — and never the primitives underneath
it. All three reports reach it as an attribute of the shared ``apex.habitat.permissions``
module, so one patch reaches all three. A report that resolves its scope any other way
never observes the patched seam: its filter does not narrow with it and its case fails.
So the suite is red precisely when the one authority and a private copy disagree, which
is the property the duplication destroyed.

Patching the PRIMITIVES instead would not detect this. Both spellings bottom out in the
same two functions, so a stubbed primitive is honoured by the copy and by the seam alike
and the two shapes stay indistinguishable — which is how the duplication survived the
existing suites. ``apex/tests/test_report_scope.py`` stubs the primitives and passes
either way; it proves the FILTER is right, this file proves WHERE the filter came from.

:class:`TestHousingAssignmentReportScopeIntegration` then drives the real permission
layer with real User Permissions and asserts the row counts a building-scoped user
actually gets back, including a widening control: granting a second building must change
the count.

Run standalone:
  bench --site <site> run-tests --module apex.habitat.report.test_housing_assignment_report_scope
"""

import unittest
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.habitat import permissions
from apex.habitat.report.accommodation_occupancy_summary import (
    accommodation_occupancy_summary as R_occupancy,
)
from apex.habitat.report.active_resident_register import active_resident_register as R_resident
from apex.habitat.report.idle_resident_detection import idle_resident_detection as R_idle
from apex.tests._helpers import _user
from apex.tests.factories import make_assignment, make_project, purge_doc

# The building column each report narrows. Accommodation Occupancy Summary queries
# Building itself, so its estate column is the primary key rather than a link.
RESIDENT_COLUMN = "building"
IDLE_COLUMN = "building"
OCCUPANCY_COLUMN = "name"


def _last_filters(mock_get_all):
    """The ``filters`` dict handed to the LAST frappe.get_all call.

    Every report short-circuits to an empty result when its first query returns
    nothing, so with get_all stubbed empty the last call IS the scoped one.
    """
    return mock_get_all.call_args.kwargs["filters"]


class TestHousingAssignmentReportsRouteThroughTheSeam(FrappeTestCase):
    """Each report's row filter must come from ``report_building_scope`` itself."""

    # [#lz1v52]

    def _filters_with_seam(self, report, verdict):
        """Run ``report.execute`` with the seam stubbed to ``verdict`` and return the
        filters it built, with get_all stubbed so nothing touches the database."""
        with patch.object(
            permissions, "report_building_scope", return_value=verdict
        ) as seam, patch.object(report.frappe, "get_all", return_value=[]) as ga:
            report.execute({})
            # A report that resolved its scope privately would leave this at zero.
            self.assertTrue(
                seam.called,
                f"{report.__name__} never called report_building_scope — it is scoping "
                "by a private copy, so a change to the seam will not reach it",
            )
            return _last_filters(ga)

    def test_resident_register_narrows_with_the_seam(self):
        filters = self._filters_with_seam(R_resident, (True, ["B-1", "B-2"]))
        self.assertEqual(filters[RESIDENT_COLUMN], ["in", ["B-1", "B-2"]])

    def test_idle_detection_narrows_with_the_seam(self):
        filters = self._filters_with_seam(R_idle, (True, ["B-1", "B-2"]))
        self.assertEqual(filters[IDLE_COLUMN], ["in", ["B-1", "B-2"]])

    def test_occupancy_summary_narrows_with_the_seam(self):
        filters = self._filters_with_seam(R_occupancy, (True, ["B-1", "B-2"]))
        self.assertEqual(filters[OCCUPANCY_COLUMN], ["in", ["B-1", "B-2"]])

    # [#kdg2pi]

    def test_a_narrower_seam_narrows_every_report(self):
        """THE DRIFT CASE. Narrow the seam from two buildings to one; every report's
        filter must follow. A report carrying its own copy keeps the wide answer."""
        wide = {
            R_resident: (RESIDENT_COLUMN, self._filters_with_seam(R_resident, (True, ["B-1", "B-2"]))),
            R_idle: (IDLE_COLUMN, self._filters_with_seam(R_idle, (True, ["B-1", "B-2"]))),
            R_occupancy: (OCCUPANCY_COLUMN, self._filters_with_seam(R_occupancy, (True, ["B-1", "B-2"]))),
        }
        for report, (column, wide_filters) in wide.items():
            with self.subTest(report=report.__name__):
                narrow_filters = self._filters_with_seam(report, (True, ["B-1"]))
                self.assertEqual(narrow_filters[column], ["in", ["B-1"]])
                self.assertNotEqual(
                    narrow_filters[column],
                    wide_filters[column],
                    "the report did not follow the seam when it narrowed",
                )

    def test_an_empty_seam_returns_no_rows(self):
        """A scoped user holding no building sees nothing — fail CLOSED, and without
        querying at all."""
        for report in (R_resident, R_idle, R_occupancy):
            with self.subTest(report=report.__name__):
                with patch.object(
                    permissions, "report_building_scope", return_value=(True, [])
                ), patch.object(report.frappe, "get_all", return_value=[]) as ga:
                    _, rows = report.execute({})[:2]
                    self.assertEqual(rows, [])
                    ga.assert_not_called()

    def test_an_out_of_scope_filter_returns_no_rows(self):
        """Asking for a building the seam did not grant yields nothing, never the
        unfiltered set."""
        for report in (R_resident, R_idle, R_occupancy):
            with self.subTest(report=report.__name__):
                with patch.object(
                    permissions, "report_building_scope", return_value=(True, ["B-1"])
                ), patch.object(report.frappe, "get_all", return_value=[]) as ga:
                    _, rows = report.execute({"building": "B-9"})[:2]
                    self.assertEqual(rows, [])
                    ga.assert_not_called()

    def test_oversight_is_not_narrowed(self):
        """NEGATIVE CONTROL. An unrestricted seam must leave the estate column out of
        the filter entirely — otherwise every case above would pass on a report that
        simply always filters."""
        for report, column in (
            (R_resident, RESIDENT_COLUMN),
            (R_idle, IDLE_COLUMN),
            (R_occupancy, OCCUPANCY_COLUMN),
        ):
            with self.subTest(report=report.__name__):
                filters = self._filters_with_seam(report, (False, []))
                self.assertNotIn(column, filters)


def _grant(user, building):
    if not frappe.db.exists(
        "User Permission", {"allow": "Building", "for_value": building, "user": user}
    ):
        frappe.get_doc(
            {
                "doctype": "User Permission",
                "allow": "Building",
                "for_value": building,
                "user": user,
            }
        ).insert(ignore_permissions=True)


class TestHousingAssignmentReportScopeIntegration(FrappeTestCase):
    """Real buildings, real submitted assignments, real User Permissions, real counts."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.tag = frappe.generate_hash(length=12).upper()

        cls.company = frappe.db.get_value("Company", {})
        cost_center = frappe.db.get_value("Cost Center", {"is_group": 0, "company": cls.company})
        cls.site = frappe.get_doc(
            {"doctype": "Site", "site_name": "HAS " + cls.tag}
        ).insert(ignore_permissions=True).name

        cls.bld_a, cls.bld_b = (
            frappe.get_doc(
                {
                    "doctype": "Building",
                    "building_name": "HAS B" + suffix + " " + cls.tag,
                    "site": cls.site,
                    "company": cls.company,
                    "total_capacity": 10,
                    "default_cost_center": cost_center,
                    "annual_rent": 36500,
                }
            ).insert(ignore_permissions=True).name
            for suffix in ("A", "B")
        )

        # Idle Resident Detection only surfaces an assignment whose project has ENDED,
        # so the shared project is parked in a terminal status for both estates.
        cls.project = make_project("HAS Ended " + cls.tag)
        frappe.db.set_value("Project", cls.project, "status", "Completed")

        cls.emp_a = cls._employee("A")
        cls.emp_b = cls._employee("B")
        cls.asg_a = make_assignment(cls.emp_a, cls.bld_a, cls.project)
        cls.asg_b = make_assignment(cls.emp_b, cls.bld_b, cls.project)

        cls.sup = _user("has_res_sup@example.com", "Resident Supervisor")
        _grant(cls.sup, cls.bld_a)
        cls.mgr = _user("has_acc_mgr@example.com", "Accommodation Manager")

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        frappe.db.delete(
            "User Permission",
            {"allow": "Building", "for_value": ["in", (cls.bld_a, cls.bld_b)], "user": cls.sup},
        )
        for asg in (cls.asg_a, cls.asg_b):
            purge_doc("Housing Assignment", asg)
        frappe.db.commit()
        super().tearDownClass()

    @classmethod
    def _employee(cls, suffix):
        return frappe.get_doc(
            {
                "doctype": "Employee",
                "employee_name": "HAS Emp " + suffix + " " + cls.tag,
                "first_name": "HAS" + suffix,
                "company": cls.company,
                "status": "Active",
                "gender": "Male",
                "date_of_joining": "2024-01-01",
                "date_of_birth": "1990-01-01",
            }
        ).insert(ignore_permissions=True).name

    def tearDown(self):
        frappe.set_user("Administrator")

    def _as(self, user):
        """Switch to ``user`` with the request-scoped User Permission cache cleared, so
        a grant made mid-test is actually re-resolved rather than served stale."""
        frappe.set_user("Administrator")
        frappe.local.cache.pop("apex_allowed_buildings", None)
        frappe.set_user(user)
        frappe.local.cache.pop("apex_allowed_buildings", None)

    def _seeded(self, rows, key="building"):
        return [r for r in rows if r.get(key) in (self.bld_a, self.bld_b)]

    # [#b52yr6]

    def test_resident_register_scoped_user_sees_only_his_building(self):
        self._as(self.sup)
        rows = self._seeded(R_resident.execute({})[1])
        self.assertEqual({r["building"] for r in rows}, {self.bld_a})
        self.assertEqual(len(rows), 1)

    def test_resident_register_oversight_sees_both(self):
        self._as(self.mgr)
        rows = self._seeded(R_resident.execute({})[1])
        self.assertEqual({r["building"] for r in rows}, {self.bld_a, self.bld_b})
        self.assertEqual(len(rows), 2)

    def test_resident_register_widening_the_grant_changes_the_count(self):
        """NEGATIVE CONTROL. The one-row result above must be caused by the User
        Permission, not by the fixture: grant the second building and the same query as
        the same user returns two rows."""
        self._as(self.sup)
        before = len(self._seeded(R_resident.execute({})[1]))

        frappe.set_user("Administrator")
        _grant(self.sup, self.bld_b)
        self.addCleanup(
            frappe.db.delete,
            "User Permission",
            {"allow": "Building", "for_value": self.bld_b, "user": self.sup},
        )

        self._as(self.sup)
        after = self._seeded(R_resident.execute({})[1])
        self.assertEqual(before, 1)
        self.assertEqual(len(after), 2)
        self.assertEqual({r["building"] for r in after}, {self.bld_a, self.bld_b})

    # [#cxlwka]

    def test_idle_detection_scoped_user_sees_only_his_building(self):
        self._as(self.sup)
        rows = self._seeded(R_idle.execute({})[1])
        self.assertEqual({r["building"] for r in rows}, {self.bld_a})

    def test_idle_detection_oversight_sees_both(self):
        self._as(self.mgr)
        rows = self._seeded(R_idle.execute({})[1])
        self.assertEqual({r["building"] for r in rows}, {self.bld_a, self.bld_b})

    # [#kdg2pi]

    def test_occupancy_summary_scoped_user_sees_only_his_building(self):
        self._as(self.sup)
        rows = self._seeded(R_occupancy.execute({})[1])
        self.assertEqual({r["building"] for r in rows}, {self.bld_a})

    def test_occupancy_summary_oversight_sees_both(self):
        self._as(self.mgr)
        rows = self._seeded(R_occupancy.execute({})[1])
        self.assertEqual({r["building"] for r in rows}, {self.bld_a, self.bld_b})


if __name__ == "__main__":
    unittest.main()
