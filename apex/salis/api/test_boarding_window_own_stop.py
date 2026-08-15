# Copyright (c) 2026, AFMCO and contributors
"""The worker's stop and the driver's stop have to be the same row.

``boarding_window.resolve`` decides whether a worker may self-confirm by joining the
driver's Trip Stop Progress rows to the worker's own stop on ``route_stop``. The driver's
rows key on the DISPATCH TRIP's copy of the route — ``copy_route_stops`` gives every trip
its own Route Stop children, and ``_resolve_trip_route_stop`` resolves under that parent
first. The worker's stop was resolved off the ROUTE PLAN instead, so the two names came
from different parents and the join never matched:

  * the per-stop half of the window never closed when the driver marked the stop done, and
  * the ``arrived`` flag never reached the worker's own window (the realtime push still
    fired, so a worker holding an open socket saw it; a worker whose phone re-polled did
    not).

These cases build both parents for one trip and assert the window follows the driver's
row. The legacy fallback is asserted too: a trip with no stop copies of its own — every
trip predating ``copy_route_stops`` — must still resolve off the Route Plan.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today

from apex.salis.api import boarding_window


class TestTheWorkerStopIsTheDriverStop(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self.building = self._building()
        self.project = self._project()
        self.route_plan = self._route_plan()
        self.trip = self._trip(with_own_stops=True)

    def _new(self, doctype, **values):
        doc = frappe.get_doc({"doctype": doctype, **values}).insert(
            ignore_permissions=True, ignore_mandatory=True
        )
        self.addCleanup(frappe.delete_doc, doctype, doc.name, force=True, ignore_permissions=True)
        return doc

    def _building(self):
        return self._new(
            "Building",
            building_name="_BW " + frappe.generate_hash(length=8).upper(),
        ).name

    def _stop_row(self):
        return {
            "stop_key": "stop-1",
            "stop_name": "_BW Pickup",
            "accommodation_building": self.building,
        }

    def _project(self):
        """Borrowed, never built: ERPNext's Project fixture is not idempotent, so a
        second insert of the same name fails rather than resolving to the first."""
        existing = frappe.db.get_value("Project", {}, "name")
        if existing:
            return existing
        return self._new(
            "Project", project_name="_BW Project " + frappe.generate_hash(length=6).upper()
        ).name

    def _route_plan(self):
        return self._new(
            "Route Plan",
            plan_name="_BW Plan " + frappe.generate_hash(length=6).upper(),
            project=self.project,
            stops=[self._stop_row()],
        ).name

    def _trip(self, with_own_stops):
        values = {
            "trip_date": today(),
            "status": "Planned",
            "project": self.project,
            "route_plan": self.route_plan,
        }
        if with_own_stops:
            values["stops"] = [self._stop_row()]
        return self._new("Dispatch Trip", **values).name

    def _stop_name(self, parent, parenttype):
        return frappe.db.get_value(
            "Route Stop",
            {
                "parent": parent,
                "parenttype": parenttype,
                "accommodation_building": self.building,
            },
            "name",
        )

    def _driver_marked(self, route_stop, **flags):
        """The driver's own record of this stop, keyed exactly as the portal writes it."""
        log = self._new(
            "Trip Start Log",
            dispatch_trip=self.trip,
            stop_progress=[
                {"sequence": 1, "stop_name": "_BW Pickup", "route_stop": route_stop, **flags}
            ],
        )
        return log.name

    def test_the_window_resolves_the_stop_the_driver_writes_against(self):
        """The defect. Both parents carry a stop for this building; only one is joinable."""
        own = boarding_window._own_stop(self.trip, None, self.building)

        self.assertIsNotNone(own)
        self.assertEqual(
            own["name"],
            self._stop_name(self.trip, "Dispatch Trip"),
            "the worker's stop came from the Route Plan, which the driver never writes to",
        )
        self.assertNotEqual(own["name"], self._stop_name(self.route_plan, "Route Plan"))

    def test_a_stop_the_driver_closed_reaches_the_worker_window(self):
        """The consequence: with the two names apart, the window never saw the stop end."""
        trip_stop = self._stop_name(self.trip, "Dispatch Trip")
        self._driver_marked(trip_stop, arrived=1, done=1, done_at=frappe.utils.now_datetime())

        window = boarding_window.resolve(self.trip, None, self.building)

        self.assertEqual(
            window["state"],
            boarding_window.DEPARTED,
            "the driver closed this stop and the worker's window did not notice",
        )
        self.assertFalse(window["can_confirm"])

    def test_the_drivers_arrival_reaches_the_worker_window(self):
        """The other half of the same join: arrival, not just departure."""
        trip_stop = self._stop_name(self.trip, "Dispatch Trip")
        self._driver_marked(trip_stop, arrived=1, arrived_at=frappe.utils.now_datetime())

        window = boarding_window.resolve(self.trip, None, self.building)

        self.assertTrue(window["arrived"], "the driver's arrival never reached this worker")

    def test_a_legacy_trip_with_no_stop_copies_still_resolves_off_the_route_plan(self):
        """The fallback the trip-first read must not remove: trips predating
        ``copy_route_stops`` carry no stops of their own.

        The state has to be made rather than inserted — ``validate`` copies the plan's
        stops onto every trip that names one, so the ORM cannot produce a modern trip
        without them. The rows are dropped afterwards, which is exactly the shape the
        old records are in on disk."""
        legacy = self._trip(with_own_stops=False)
        frappe.db.delete("Route Stop", {"parent": legacy, "parenttype": "Dispatch Trip"})
        self.assertIsNone(
            self._stop_name(legacy, "Dispatch Trip"), "the legacy state was not reached"
        )

        own = boarding_window._own_stop(legacy, None, self.building)

        self.assertIsNotNone(own, "a legacy trip lost its stop entirely")
        self.assertEqual(own["name"], self._stop_name(self.route_plan, "Route Plan"))
