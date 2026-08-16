# Copyright (c) 2026, afmcoltd

"""Tests for the Passenger Manifest Register report.

Pins the report's mechanical contract: every column's fieldname must be a key
on each passenger row ``execute()`` returns, and the project scope guard
(resolved through the manifest's Route Plan) must confine a scoped caller
holding no Project User Permission to zero rows while still handing back the
column definitions.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.salis.report.passenger_manifest_register.passenger_manifest_register import execute
from apex.tests._helpers import _user, as_user
from apex.tests.factories import make_project, make_vehicle


def _driver(full_name):
    """Get-or-create an Active Salis Driver carrying no Employee link; return its name."""
    existing = frappe.db.get_value("Salis Driver", {"full_name": full_name}, "name")
    if existing:
        return existing
    return (
        frappe.get_doc({"doctype": "Salis Driver", "full_name": full_name, "status": "Active"})
        .insert(ignore_permissions=True)
        .name
    )


def _route_plan(route_name, project):
    """Get-or-create a Route Plan carrying ``project``; return its name."""
    existing = frappe.db.get_value("Route Plan", {"route_name": route_name}, "name")
    if existing:
        return existing
    return (
        frappe.get_doc({"doctype": "Route Plan", "route_name": route_name, "project": project})
        .insert(ignore_permissions=True)
        .name
    )


def _submitted_manifest(route_plan, vehicle, driver, dispatch_trip=None):
    """Insert and submit a Passenger Manifest with one boarded passenger row."""
    doc = frappe.get_doc(
        {
            "doctype": "Passenger Manifest",
            "route_plan": route_plan,
            "dispatch_trip": dispatch_trip,
            "vehicle": vehicle,
            "driver": driver,
            "dispatch_date": frappe.utils.today(),
        }
    )
    doc.append(
        "passengers",
        {
            "passenger_name": "A564 PM Passenger",
            "pickup": "Gate 1",
            "dropoff": "Site A",
            "boarded": 1,
        },
    )
    doc.insert(ignore_permissions=True)
    doc.submit()
    return doc


def _dispatch_trip(project, route_plan, vehicle, driver):
    """Get-or-create a Dispatch Trip carrying ``project``; return its name."""
    return (
        frappe.get_doc(
            {
                "doctype": "Dispatch Trip",
                "trip_type": "Ad Hoc",
                "trip_date": frappe.utils.today(),
                "project": project,
                "route_plan": route_plan,
                "vehicle": vehicle,
                "driver": driver,
            }
        )
        .insert(ignore_permissions=True)
        .name
    )


class TestPassengerManifestRegister(FrappeTestCase):
    """Exercises the register's column/row contract and its project scope guard."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.project = make_project("A564 PMR Project")
        cls.route_plan = _route_plan("A564 PMR Route", cls.project)
        cls.vehicle = make_vehicle("A564-PMR-1", project=cls.project)
        cls.driver = _driver("A564 PMR Driver")
        cls.manifest = _submitted_manifest(cls.route_plan, cls.vehicle, cls.driver)

    def setUp(self):
        """Runs every case as Administrator, regardless of what the previous case switched to."""
        frappe.set_user("Administrator")

    def tearDown(self):
        """Restores the Administrator session after a case that switched users."""
        frappe.set_user("Administrator")

    def test_columns_and_row_fieldnames_agree(self):
        """Every column's fieldname must be a key on each passenger row execute() returns."""
        columns, rows, _chart, _report_summary, _summary = execute({"route_plan": self.route_plan})

        self.assertTrue(rows, "the fixture manifest's passenger must be visible to an unscoped caller")
        fieldnames = {column["fieldname"] for column in columns}
        for row in rows:
            missing = fieldnames - set(row.keys())
            self.assertEqual(missing, set(), f"row is missing declared column fieldnames: {missing}")

    def test_out_of_scope_caller_gets_columns_and_no_rows(self):
        """A project-scoped caller holding no Project User Permission sees zero rows."""
        outsider = _user("a564-pmr-outsider@test.local", "Fleet Supervisor")
        with as_user(outsider):
            columns, rows, _chart, _report_summary, summary = execute({"route_plan": self.route_plan})

        self.assertTrue(columns, "columns must still be returned to an out-of-scope caller")
        self.assertEqual(rows, [])
        self.assertEqual(summary[0]["value"], 0)

    def test_scope_follows_the_trip_project_not_the_route_plan_project(self):
        """A manifest whose Dispatch Trip sits in a DIFFERENT project than its Route
        Plan must be scoped by the trip -- the same axis the desk list hook uses --
        or this register and the desk list disagree on the same document."""
        other_project = make_project("A564 PMR Other Project")
        trip = _dispatch_trip(other_project, self.route_plan, self.vehicle, self.driver)
        manifest = _submitted_manifest(self.route_plan, self.vehicle, self.driver, dispatch_trip=trip)

        def _purge():
            manifest.cancel()
            frappe.delete_doc("Passenger Manifest", manifest.name, force=True, ignore_permissions=True)

        self.addCleanup(_purge)

        insider = _user("a564-pmr-other-insider@test.local", "Fleet Supervisor")
        frappe.get_doc(
            {"doctype": "User Permission", "user": insider, "allow": "Project", "for_value": other_project}
        ).insert(ignore_permissions=True)
        with as_user(insider):
            _columns, rows, _chart, _report_summary, _summary = execute({})
        self.assertIn(
            manifest.name,
            {row["name"] for row in rows},
            "a caller scoped to the trip's own project must see the manifest",
        )

        outsider = _user("a564-pmr-route-only-outsider@test.local", "Fleet Supervisor")
        frappe.get_doc(
            {"doctype": "User Permission", "user": outsider, "allow": "Project", "for_value": self.project}
        ).insert(ignore_permissions=True)
        with as_user(outsider):
            _columns, rows, _chart, _report_summary, _summary = execute({})
        self.assertNotIn(
            manifest.name,
            {row["name"] for row in rows},
            "a caller scoped only to the route plan's project must not see a manifest whose trip sits elsewhere",
        )
