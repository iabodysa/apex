# Copyright (c) 2026, afmcoltd

"""Pins the Trip Start Register's project scope to the Dispatch Trip it names,
the same axis SALIS_SCOPE["Trip Start Log"] (permissions.py _trip_child())
projects the desk list through -- a borrowed driver running an in-scope trip
must stay visible here, and an in-scope driver running an out-of-scope trip
must stay hidden."""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.salis.report.trip_start_register.trip_start_register import execute
from apex.tests._helpers import _user, as_user
from apex.tests.factories import make_project, make_vehicle


def _driver(full_name, project):
    existing = frappe.db.get_value("Salis Driver", {"full_name": full_name}, "name")
    if existing:
        return existing
    return (
        frappe.get_doc(
            {
                "doctype": "Salis Driver",
                "full_name": full_name,
                "status": "Active",
                "project": project,
            }
        )
        .insert(ignore_permissions=True)
        .name
    )


def _dispatch_trip(project, vehicle, driver):
    return (
        frappe.get_doc(
            {
                "doctype": "Dispatch Trip",
                "trip_type": "Ad Hoc",
                "trip_date": frappe.utils.today(),
                "project": project,
                "vehicle": vehicle,
                "driver": driver,
            }
        )
        .insert(ignore_permissions=True)
        .name
    )


def _trip_start_log(dispatch_trip, driver, vehicle):
    return frappe.get_doc(
        {
            "doctype": "Trip Start Log",
            "dispatch_trip": dispatch_trip,
            "driver": driver,
            "vehicle": vehicle,
            "trip_date": frappe.utils.today(),
            "status": "Started",
        }
    ).insert(ignore_permissions=True)


class TestTripStartRegisterProjectScope(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.trip_project = make_project("A557 TSR Trip Project")
        cls.driver_project = make_project("A557 TSR Driver Project")
        cls.vehicle = make_vehicle("A557-TSR-1", project=cls.trip_project)

    def setUp(self):
        frappe.set_user("Administrator")

    def tearDown(self):
        frappe.set_user("Administrator")

    def test_scope_follows_the_trip_project_not_the_driver_project(self):
        """A driver whose own project differs from the trip they are running:
        the register must scope on the TRIP's project, matching the desk list."""
        driver = _driver("A557 TSR Borrowed Driver", self.driver_project)
        trip = _dispatch_trip(self.trip_project, self.vehicle, driver)
        log = _trip_start_log(trip, driver, self.vehicle)
        self.addCleanup(lambda: frappe.delete_doc("Trip Start Log", log.name, force=True, ignore_permissions=True))

        insider = _user("a557-tsr-trip-insider@test.local", "Fleet Supervisor")
        frappe.get_doc(
            {"doctype": "User Permission", "user": insider, "allow": "Project", "for_value": self.trip_project}
        ).insert(ignore_permissions=True)
        with as_user(insider):
            _columns, rows, _chart, _report_summary, _summary = execute()
        self.assertIn(
            trip,
            {row["dispatch_trip"] for row in rows},
            "a caller scoped to the trip's own project must see this log",
        )

        outsider = _user("a557-tsr-driver-only-outsider@test.local", "Fleet Supervisor")
        frappe.get_doc(
            {
                "doctype": "User Permission",
                "user": outsider,
                "allow": "Project",
                "for_value": self.driver_project,
            }
        ).insert(ignore_permissions=True)
        with as_user(outsider):
            # No trip exists in the outsider's own project, so the report's
            # zero-in-scope-trips guard short-circuits to (columns, []).
            rows = execute()[1]
        self.assertFalse(
            any(r.get("dispatch_trip") == trip for r in rows),
            "a caller scoped only to the driver's own project must not see a log for a trip run elsewhere",
        )
