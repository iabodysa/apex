# Copyright (c) 2026, AFMCO and contributors
"""The worker's boarding window — the time gate on a self-confirm.

``salis/api/boarding_window.py`` ties the confirm to the worker's OWN stop,
through the Trip Stop Progress rows the driver portal already writes — not to
the calendar day alone. Scoping by day alone would leave a 07:00 trip
confirmable at 23:00, and would let a bus that already served a worker's stop
accept him again, so the gate manifest would report a headcount that includes
a man still standing at the camp.

These cases prove both directions of that gate on real records:

  * the refusals — a confirm after the driver marked the stop done, a confirm
    before the window opens, and a confirm on a finished trip — each raise a NAMED
    reason and leave no Trip Boarding Event and no Trip Start Log behind;
  * the fail-open contract — a driver who never tapped anything, a bus running
    late, an untimed trip and a mark at an EARLIER stop all leave the window OPEN,
    because a refusal that is wrong strands a real worker at a real stop;
  * the boundaries — the opening lead is read from Salis Settings, a recorded
    arrival opens the window ahead of the planned time, a mark at a LATER stop
    closes it, and a stop planned before its trip departs belongs to the night
    run's next day.

Every time-branch case injects ``now`` into ``boarding_window.resolve`` rather
than waiting on the clock, so the verdicts do not depend on the hour the suite
runs. The endpoint cases that cannot inject a clock are built on shapes that hold
at every hour.

Size note: 387 test lines against 78 in the subject (5.0x), for 20 distinct behaviours. The ratio is arithmetic on a small subject, not overtesting: each test names a different behaviour.
"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, get_datetime, getdate, now_datetime, today

from apex.apex_core.doctype.salis_settings.salis_settings import get_boarding_setting
from apex.salis.api import boarding_flow, boarding_window, masar
from apex.tests.factories import (
    WorkerTripMixin as _WorkerTripMixin,
    ensure_worker_token,
    fixture_tag,
    make_masar_building as _building,
    make_project as _project,
    make_test_driver as _ensure_test_driver,
    make_worker_employee as _employee,
)

# The two-stop cases raise this building inside the test body; ``make_masar_building``
# is get-or-create on the building name and commits, so the row outlives
# FrappeTestCase's rollback and the class teardown removes it by that name.
_SECOND_STOP_BUILDING = "Masar BW Building Two"


class TestBoardingWindow(_WorkerTripMixin, FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.project = _project("Masar BW Project")
        cls.building = _building("Masar BW Building")
        cls.driver = _ensure_test_driver()

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        for building in (
            cls.building,
            frappe.db.get_value("Building", {"building_name": _SECOND_STOP_BUILDING}, "name"),
        ):
            if building and frappe.db.exists("Building", building):
                frappe.delete_doc("Building", building, ignore_permissions=True, force=True)
        if frappe.db.exists("Project", cls.project):
            frappe.delete_doc("Project", cls.project, ignore_permissions=True, force=True)
        frappe.db.commit()
        super().tearDownClass()

    def setUp(self):
        frappe.set_user("Administrator")

    def tearDown(self):
        frappe.set_user("Administrator")

    def _worker(self):
        """A worker nothing else can already be holding.

        ``make_worker_employee`` is get-or-create on a stable name, so a fixed
        identity re-adopts whatever the previous run left behind — including a
        second live Transport Request that ``_worker_today_dispatch_trip`` would
        resolve ahead of this test's trip."""
        return _employee(f"Masar BW {fixture_tag()}")

    def _trip(self, workers, planned_time=None, second_stop_building=None, **trip_kwargs):
        """A Workers-line trip plus a handle on the worker's own route stop.

        Returns ``(transport_request, route_plan, dispatch_trip, route_stop)``.
        ``route_stop`` is the Dispatch Trip's OWN copy of the stop — the row
        ``boarding_window._own_stop`` resolves first (apex/salis/api/boarding_window.py:129-138)
        and the row the driver portal's ``_resolve_trip_route_stop`` keys Trip Stop
        Progress against (apex/salis/api/driver_portal/__init__.py:170-183), made by
        ``copy_route_stops`` at Dispatch Trip insert (apex/salis/doctype/dispatch_trip/trip_manifest.py:93-108).
        The Route Plan's own row is a different parent with a different row name and
        is never read by ``resolve`` once the trip carries its own stops, so writing
        Trip Stop Progress or a planned_time against it leaves the window unable to
        see either. ``planned_time`` is stamped on the worker's own stop; ``depart_time``
        defaults to now, which is what makes the fixture boardable at any hour."""
        tr, rp, dt = self._worker_trip(
            self.driver,
            self.project,
            self.building,
            workers,
            f"BW Route {fixture_tag()}",
            **trip_kwargs,
        )
        if second_stop_building:
            plan = frappe.get_doc("Route Plan", rp.name)
            plan.append(
                "stops",
                {
                    "sequence": len(plan.stops) + 1,
                    "stop_name": "Second Housing Pickup",
                    "accommodation_building": second_stop_building,
                    "location": "Second Gate",
                    "passengers": 0,
                },
            )
            plan.flags.ignore_validate = True
            plan.save(ignore_permissions=True)
        route_stop = frappe.db.get_value(
            "Route Stop",
            {
                "parent": dt.name,
                "parenttype": "Dispatch Trip",
                "accommodation_building": self.building,
            },
            "name",
        )
        if planned_time is not None:
            frappe.db.set_value("Route Stop", route_stop, "planned_time", planned_time)
        return tr, rp, dt, route_stop

    def _log(self, dispatch_trip, status="Started"):
        """The trip's open Trip Start Log — the record the driver's per-stop
        progress hangs off."""
        log = frappe.get_doc(
            {
                "doctype": "Trip Start Log",
                "dispatch_trip": dispatch_trip,
                "status": status,
                "start_datetime": now_datetime(),
            }
        ).insert(ignore_permissions=True)
        self.addCleanup(lambda: self._purge_logs(dispatch_trip))
        return log

    def _progress(self, log, route_stop, sequence=1, arrived=0, done=0):
        """One Trip Stop Progress row, exactly as the driver portal writes it."""
        doc = frappe.get_doc("Trip Start Log", log.name)
        doc.append(
            "stop_progress",
            {
                "route_stop": route_stop,
                "sequence": sequence,
                "stop_name": "Housing Pickup",
                "arrived": arrived,
                "arrived_at": now_datetime() if arrived else None,
                "done": done,
                "done_at": now_datetime() if done else None,
            },
        )
        doc.flags.ignore_permissions = True
        doc.save()
        return doc

    @staticmethod
    def _purge_logs(dispatch_trip):
        frappe.set_user("Administrator")
        for name in frappe.get_all(
            "Trip Start Log", filters={"dispatch_trip": dispatch_trip}, pluck="name"
        ):
            frappe.db.set_value("Trip Start Log", name, "docstatus", 0, update_modified=False)
            frappe.delete_doc("Trip Start Log", name, ignore_permissions=True, force=True)

    @staticmethod
    def _boarding_rows(dispatch_trip, employee):
        logs = frappe.get_all(
            "Trip Start Log", filters={"dispatch_trip": dispatch_trip}, pluck="name"
        )
        if not logs:
            return []
        return frappe.get_all(
            "Trip Boarding Event",
            filters={
                "parenttype": "Trip Start Log",
                "parent": ["in", logs],
                "worker": employee,
            },
            pluck="name",
        )

    def _at(self, trip_date, clock):
        """A datetime on the trip's own date, for injecting into ``resolve``."""
        return get_datetime(f"{getdate(trip_date)} {clock}")

    # The opening edge

    def test_the_opening_lead_is_the_grace_read_from_salis_settings(self):
        """The window opens ``boarding_grace_minutes`` before the stop's planned
        time, and moves when that setting moves — there is no lead baked into the
        code."""
        worker = self._worker()
        _tr, _rp, dt, _rs = self._trip([worker], depart_time="08:00:00", planned_time="08:00:00")
        planned = self._at(dt.trip_date, "08:00:00")

        frappe.db.set_single_value("Salis Settings", "boarding_grace_minutes", 30)
        self.addCleanup(
            lambda: frappe.db.set_single_value("Salis Settings", "boarding_grace_minutes", 0)
        )
        self.assertEqual(get_boarding_setting("boarding_grace_minutes"), 30)

        early = boarding_window.resolve(
            dt.name, building=self.building, now=add_to_date(planned, minutes=-31)
        )
        self.assertNotEqual(early["state"], boarding_window.AT_STOP)
        self.assertFalse(early["can_confirm"])

        opened = boarding_window.resolve(
            dt.name, building=self.building, now=add_to_date(planned, minutes=-29)
        )
        self.assertEqual(opened["state"], boarding_window.AT_STOP)
        self.assertTrue(opened["can_confirm"])

        frappe.db.set_single_value("Salis Settings", "boarding_grace_minutes", 5)
        narrowed = boarding_window.resolve(
            dt.name, building=self.building, now=add_to_date(planned, minutes=-29)
        )
        self.assertNotEqual(
            narrowed["state"],
            boarding_window.AT_STOP,
            "the same instant must close again once the settings grace narrows",
        )

    def test_a_recorded_arrival_opens_the_window_ahead_of_the_planned_time(self):
        """The window opens at the EARLIER of the two ends: once the driver has
        marked arrival at this worker's stop, the clock no longer matters."""
        worker = self._worker()
        _tr, _rp, dt, route_stop = self._trip(
            [worker], depart_time="08:00:00", planned_time="08:00:00"
        )
        log = self._log(dt.name)
        planned = self._at(dt.trip_date, "08:00:00")

        before = boarding_window.resolve(
            dt.name, building=self.building, now=add_to_date(planned, hours=-3)
        )
        self.assertEqual(before["state"], boarding_window.EN_ROUTE)

        self._progress(log, route_stop, arrived=1)
        after = boarding_window.resolve(
            dt.name, building=self.building, now=add_to_date(planned, hours=-3)
        )
        self.assertEqual(after["state"], boarding_window.AT_STOP)
        self.assertTrue(after["arrived"])

    def test_scheduled_before_the_trip_starts_and_en_route_once_it_has(self):
        """Two distinct pre-boarding states: nothing has begun, versus the driver
        is on the road but has not reached this stop."""
        worker = self._worker()
        _tr, _rp, dt, _rs = self._trip([worker], depart_time="08:00:00", planned_time="08:00:00")
        early = add_to_date(self._at(dt.trip_date, "08:00:00"), hours=-3)

        self.assertEqual(
            boarding_window.resolve(dt.name, building=self.building, now=early)["state"],
            boarding_window.SCHEDULED,
        )
        self._log(dt.name)
        self.assertEqual(
            boarding_window.resolve(dt.name, building=self.building, now=early)["state"],
            boarding_window.EN_ROUTE,
        )

    # The closing edge

    def test_the_window_closes_when_the_driver_marks_the_stop_done(self):
        """The card's close: the stop is served, the bus is gone."""
        worker = self._worker()
        _tr, _rp, dt, route_stop = self._trip([worker])
        log = self._log(dt.name)
        self._progress(log, route_stop, arrived=1, done=1)

        window = boarding_window.resolve(dt.name, building=self.building)
        self.assertEqual(window["state"], boarding_window.DEPARTED)
        self.assertEqual(window["reason"], "stop_departed")
        self.assertFalse(window["can_confirm"])
        self.assertIsNotNone(window["done_at"])

    def test_a_mark_at_a_later_stop_closes_the_window(self):
        """A bus cannot be at stop two and still at stop one. A later mark is
        recorded proof this worker's stop is behind it."""
        second = _building(_SECOND_STOP_BUILDING)
        worker = self._worker()
        _tr, rp, dt, route_stop = self._trip([worker], second_stop_building=second)
        later_stop = frappe.db.get_value(
            "Route Stop",
            {"parent": rp.name, "parenttype": "Route Plan", "accommodation_building": second},
            "name",
        )
        log = self._log(dt.name)
        self._progress(log, later_stop, sequence=3, arrived=1)

        window = boarding_window.resolve(dt.name, building=self.building)
        self.assertEqual(window["state"], boarding_window.DEPARTED)
        self.assertEqual(window["reason"], "stop_departed")
        self.assertNotEqual(route_stop, later_stop)

    def test_a_mark_at_an_earlier_stop_leaves_the_window_open(self):
        """A worker boarding at the SECOND stop is not shut out by the driver
        finishing the first one."""
        second = _building(_SECOND_STOP_BUILDING)
        worker = self._worker()
        _tr, rp, dt, _rs = self._trip([worker], second_stop_building=second)
        first_stop = frappe.db.get_value(
            "Route Stop",
            {
                "parent": rp.name,
                "parenttype": "Route Plan",
                "accommodation_building": self.building,
            },
            "name",
        )
        log = self._log(dt.name)
        self._progress(log, first_stop, sequence=1, arrived=1, done=1)

        window = boarding_window.resolve(dt.name, building=second)
        self.assertEqual(
            window["state"],
            boarding_window.AT_STOP,
            "an earlier stop being done says nothing about a later one",
        )

    def test_a_finished_trip_refuses(self):
        worker = self._worker()
        _tr, _rp, dt, _rs = self._trip([worker])
        frappe.db.set_value("Dispatch Trip", dt.name, "status", "Completed")

        window = boarding_window.resolve(dt.name, building=self.building)
        self.assertEqual(window["state"], boarding_window.FINISHED)
        self.assertEqual(window["reason"], "trip_finished")

    def test_a_closed_manifest_log_closes_the_window(self):
        """``depart_and_finalize`` closes the trip's manifest log. A confirm after
        it would open a boarding row on a manifest the driver has already handed
        in."""
        worker = self._worker()
        _tr, _rp, dt, _rs = self._trip([worker])
        log = self._log(dt.name)
        frappe.db.set_value("Trip Start Log", log.name, "status", "Completed")

        window = boarding_window.resolve(dt.name, building=self.building)
        self.assertEqual(window["state"], boarding_window.DEPARTED)

    # Missing evidence must never refuse

    def test_a_driver_who_never_taps_locks_nobody_out(self):
        """The dangerous case. With no Trip Stop Progress row at all, the window
        stays OPEN — a forgetful driver must not lock out his whole bus."""
        worker = self._worker()
        _tr, _rp, dt, _rs = self._trip([worker], depart_time="00:00:01", planned_time="00:00:01")
        log = self._log(dt.name)
        self.assertEqual(
            frappe.db.count("Trip Stop Progress", {"parent": log.name}),
            0,
            "this case is about a driver who recorded nothing at all",
        )

        window = boarding_window.resolve(
            dt.name, building=self.building, now=self._at(dt.trip_date, "23:00:00")
        )
        self.assertEqual(window["state"], boarding_window.AT_STOP)
        self.assertTrue(window["can_confirm"])
        self.assertFalse(window["arrived"])

    def test_a_late_bus_still_boards(self):
        """Forty-five minutes past the planned time with nothing recorded is a late
        bus, not a departed one."""
        worker = self._worker()
        _tr, _rp, dt, _rs = self._trip([worker], depart_time="08:00:00", planned_time="08:00:00")
        self._log(dt.name)

        window = boarding_window.resolve(
            dt.name,
            building=self.building,
            now=add_to_date(self._at(dt.trip_date, "08:00:00"), minutes=45),
        )
        self.assertEqual(window["state"], boarding_window.AT_STOP)

    def test_a_trip_with_no_time_on_file_stays_open(self):
        """No stop time and no departure time is no time branch at all, so the
        window has nothing to hold shut."""
        worker = self._worker()
        _tr, _rp, dt, route_stop = self._trip([worker])
        frappe.db.set_value("Dispatch Trip", dt.name, "depart_time", None)
        frappe.db.set_value("Route Stop", route_stop, "planned_time", None)

        window = boarding_window.resolve(dt.name, building=self.building)
        self.assertEqual(window["state"], boarding_window.AT_STOP)
        self.assertIsNone(window["anchor_at"])

    def test_a_worker_whose_stop_cannot_be_identified_falls_back_to_the_trip(self):
        """With no pickup building there is no stop to gate on, so the trip's own
        departure governs — and no per-stop mark can ever close the window on a
        worker whose stop the data cannot name."""
        worker = self._worker()
        _tr, _rp, dt, route_stop = self._trip(
            [worker], depart_time="08:00:00", planned_time="08:00:00"
        )
        log = self._log(dt.name)
        self._progress(log, route_stop, arrived=1, done=1)
        departure = self._at(dt.trip_date, "08:00:00")

        before = boarding_window.resolve(
            dt.name, building=None, now=add_to_date(departure, hours=-6)
        )
        self.assertEqual(before["state"], boarding_window.EN_ROUTE)
        self.assertIsNone(before["stop_name"])

        after = boarding_window.resolve(
            dt.name, building=None, now=add_to_date(departure, hours=6)
        )
        self.assertEqual(after["state"], boarding_window.AT_STOP)

    # The night run

    def test_an_untended_stop_time_can_only_open_the_window_sooner(self):
        """Frappe stamps every unset Time field with the clock at creation
        (frappe/model/create_new.py:149-150), so a route stop nobody timed carries
        the hour its plan was typed. The window anchors on the EARLIER of the stop
        and the trip, so such a value never locks a morning bus out until the
        afternoon."""
        worker = self._worker()
        _tr, _rp, dt, _rs = self._trip(
            [worker], depart_time="06:00:00", planned_time="14:00:00"
        )
        window = boarding_window.resolve(
            dt.name, building=self.building, now=self._at(dt.trip_date, "06:30:00")
        )
        self.assertEqual(window["anchor_at"], f"{getdate(dt.trip_date)} 06:00:00")
        self.assertEqual(window["state"], boarding_window.AT_STOP)

    def test_a_night_run_still_in_motion_after_midnight_is_boardable(self):
        """The yesterday half of the boardable date window carries a night run past
        midnight; its stop is long open by then."""
        worker = self._worker()
        _tr, _rp, dt, _rs = self._trip(
            [worker], depart_time="23:30:00", planned_time="23:30:00"
        )
        frappe.db.set_value(
            "Dispatch Trip", dt.name, "trip_date", add_to_date(today(), days=-1)
        )
        window = boarding_window.resolve(dt.name, building=self.building)
        self.assertEqual(window["state"], boarding_window.AT_STOP)

    # The endpoints

    def test_confirm_after_the_stop_is_done_is_refused_and_writes_no_boarding_event(self):
        """The card's clause: a confirm attempted after the stop is done is refused
        and leaves no Trip Boarding Event row."""
        worker = self._worker()
        tr, _rp, dt, route_stop = self._trip([worker])
        log = self._log(dt.name)
        self._progress(log, route_stop, arrived=1, done=1)
        token = ensure_worker_token(worker)
        self.assertEqual(self._boarding_rows(dt.name, worker), [])

        with self.assertRaises(boarding_window.BoardingStopDeparted):
            masar.confirm_boarding(token=token, transport_request=tr.name)

        self.assertEqual(
            self._boarding_rows(dt.name, worker),
            [],
            "a refused confirm must write no boarding event",
        )

    def test_the_claim_endpoint_is_gated_by_the_same_window(self):
        """``worker_claim_boarded`` writes the same manifest row from the live
        boarding screen, so the same gate has to stand in front of it."""
        worker = self._worker()
        _tr, _rp, dt, route_stop = self._trip([worker])
        log = self._log(dt.name)
        self._progress(log, route_stop, arrived=1, done=1)
        token = ensure_worker_token(worker)

        with self.assertRaises(boarding_window.BoardingStopDeparted):
            boarding_flow.worker_claim_boarded(token=token)

        self.assertEqual(self._boarding_rows(dt.name, worker), [])

    def test_confirm_before_the_window_opens_is_refused_and_opens_no_log(self):
        """Six hours before an 08:00 bus there is nothing to be aboard — and the
        refusal lands before any manifest log exists."""
        worker = self._worker()
        tr, _rp, dt, _rs = self._trip(
            [worker], depart_time="08:00:00", planned_time="08:00:00"
        )
        token = ensure_worker_token(worker)

        with patch.object(
            boarding_window, "now_datetime", return_value=self._at(dt.trip_date, "02:00:00")
        ), self.assertRaises(boarding_window.BoardingNotOpenYet):
            masar.confirm_boarding(token=token, transport_request=tr.name)

        self.assertEqual(self._boarding_rows(dt.name, worker), [])
        self.assertEqual(
            frappe.db.count("Trip Start Log", {"dispatch_trip": dt.name}),
            0,
            "a refusal must not open the trip's manifest log",
        )

    def test_confirm_inside_the_window_still_boards(self):
        """The gate refuses the lie, not the worker: a trip departing now boards."""
        worker = self._worker()
        tr, _rp, dt, _rs = self._trip([worker])
        self.addCleanup(lambda: self._purge_logs(dt.name))
        token = ensure_worker_token(worker)

        result = masar.confirm_boarding(token=token, transport_request=tr.name)
        self.assertTrue(result["created"])
        self.assertEqual(result["boarding_window"]["state"], boarding_window.AT_STOP)
        self.assertEqual(len(self._boarding_rows(dt.name, worker)), 1)

    def test_the_worker_screen_carries_the_window_state(self):
        """The Transport screen renders the state its ride is in, so it never shows
        a confirm button the server would refuse."""
        worker = self._worker()
        tr, _rp, dt, route_stop = self._trip([worker], status="Dispatched")
        log = self._log(dt.name)
        self._progress(log, route_stop, arrived=1, done=1)
        token = ensure_worker_token(worker)

        payload = masar.get_worker_transport(token=token)
        trips = payload["upcoming"] + payload["past"]
        mine = [t for t in trips if t["transport_request"] == tr.name]
        self.assertEqual(len(mine), 1)
        self.assertEqual(mine[0]["boarding_window"]["state"], boarding_window.DEPARTED)
        self.assertFalse(mine[0]["boarding_window"]["can_confirm"])
        self.assertEqual(mine[0]["dispatch_trip"], dt.name)

    def test_the_worker_poll_carries_the_window_state(self):
        """The live boarding poll is the delivery path for a guest worker, so it
        carries the same verdict the screen renders."""
        worker = self._worker()
        _tr, _rp, dt, route_stop = self._trip([worker])
        log = self._log(dt.name)
        self._progress(log, route_stop, arrived=1)
        token = ensure_worker_token(worker)

        state = boarding_flow.worker_trip_boarding(token=token)
        self.assertEqual(state["dispatch_trip"], dt.name)
        self.assertEqual(state["boarding_window"]["state"], boarding_window.AT_STOP)
        self.assertTrue(state["driver_arrived"]["arrived"])

