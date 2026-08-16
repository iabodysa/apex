# Copyright (c) 2026, AFMCO and contributors
"""Boarding/departure flow + two-sided confirmation.

Covers the server contract the driver + worker SPAs build against:

  * Salis Settings boarding tunables fall back to their built-in defaults when
    the stored Single Int is 0/unset (the new-Single-Int-stores-0 trap).
  * Feature A: a scan onto the WRONG bus returns a structured WRONG_BUS
    correction (the worker's real trip + that driver's phone) and records a
    transient misboard hint the worker poll reads.
  * Feature B: driver notify bumps notify_count capped at the max and depart
    marks an exhausted Pending worker Absent (after grace); a worker wait request
    caps at its max.
  * Worker self-confirm: the claim boards the worker immediately (no driver gate)
    and records a Worker boarding event; the driver's only intervention is the
    exception override (driver_mark_not_boarded) that reverses a self-confirm. No
    auto-confirm timeout machinery remains in ``boarding_flow.py``: self-confirm
    made the "Worker Claimed" state unreachable, and ``Trip Boarding State``
    (apex/salis/doctype/trip_boarding_state/trip_boarding_state.json:96-100) no
    longer offers it as an option.

The token-scoped worker endpoints resolve identity via masar._resolve_worker and
masar._worker_today_dispatch_trip; the tests patch those two so a real Masar
Worker Token need not be provisioned (the identity contract is exercised
elsewhere). ``test_ignore`` prunes the HR/master auto-dependency walk.

Size note: for 18 distinct behaviours, arithmetic on a small subject, not overtesting: each test names a different behaviour.
"""

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, now_datetime

from apex.apex_core.doctype.salis_settings.salis_settings import (
    BOARDING_FLOW_DEFAULTS,
    get_boarding_setting,
    get_boarding_settings,
)
from apex.salis.api import boarding_flow
from apex.salis.api.driver_portal import execution

test_ignore = [
    "Employee",
    "Company",
    "Project",
    "Salis Vehicle",
    "Salis Driver",
    "User",
    "Role",
    "Transport Request",
]


def _h(n=12):
    return frappe.generate_hash(length=n).upper()


class TestBoardingFlow(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self._cleanup = []

        self.employee = frappe.get_doc(
            {"doctype": "Employee", "first_name": "EMP-" + _h(), "naming_series": "HR-EMP-"}
        )
        self.employee.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        self._cleanup.append(("Employee", self.employee.name))

        self.driver = frappe.get_doc(
            {
                "doctype": "Salis Driver",
                "full_name": "TBF Driver " + _h(),
                "status": "Active",
                "phone": "+966500000001",
            }
        ).insert(ignore_permissions=True)
        self._cleanup.append(("Salis Driver", self.driver.name))

        self.request = frappe.get_doc({"doctype": "Transport Request", "request_date": "2026-06-20"})
        self.request.append("workers", {"employee": self.employee.name})
        self.request.flags.ignore_validate = True
        self.request.insert(
            ignore_permissions=True, ignore_links=True, ignore_mandatory=True
        )
        self._cleanup.append(("Transport Request", self.request.name))

        self.trip = frappe.get_doc(
            {
                "doctype": "Dispatch Trip",
                "naming_series": "DT-.######",
                "transport_request": self.request.name,
                "driver": self.driver.name,
                "trip_date": "2026-06-20",
                "status": "Planned",
            }
        )
        self.trip.flags.ignore_validate = True
        self.trip.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        self._cleanup.append(("Dispatch Trip", self.trip.name))

    def tearDown(self):
        frappe.set_user("Administrator")
        for tsl in frappe.get_all(
            "Trip Start Log", filters={"dispatch_trip": self.trip.name}, pluck="name"
        ):
            frappe.db.set_value("Trip Start Log", tsl, "docstatus", 0, update_modified=False)
            frappe.delete_doc("Trip Start Log", tsl, force=True, ignore_permissions=True)
        frappe.cache.delete_value("salis_misboard:" + self.employee.name)
        for dt, name in reversed(self._cleanup):
            frappe.delete_doc(dt, name, force=True, ignore_permissions=True)


    def _seed_state(self, started_minutes_ago=10):
        """Populate boarding_state from the manifest and open a Trip Start Log
        whose start is ``started_minutes_ago`` in the past (so grace can pass)."""
        log = frappe.get_doc(
            {
                "doctype": "Trip Start Log",
                "dispatch_trip": self.trip.name,
                "status": "Started",
                "start_datetime": add_to_date(now_datetime(), minutes=-started_minutes_ago),
            }
        )
        log.insert(ignore_permissions=True)
        boarding_flow.ensure_trip_boarding_state(self.trip.name)
        self.trip.reload()

    def _row(self):
        self.trip.reload()
        return next(
            (r for r in self.trip.boarding_state if r.employee == self.employee.name), None
        )


    def test_settings_fall_back_to_defaults_when_zero_or_unset(self):
        for key, default in BOARDING_FLOW_DEFAULTS.items():
            frappe.db.set_single_value("Salis Settings", key, 0)
            self.assertEqual(
                get_boarding_setting(key),
                default,
                f"{key} must fall back to its default {default} when stored 0",
            )
        self.assertEqual(get_boarding_settings(), dict(BOARDING_FLOW_DEFAULTS))

    def test_settings_honor_a_real_stored_value(self):
        frappe.db.set_single_value("Salis Settings", "boarding_notify_max_count", 5)
        self.addCleanup(
            lambda: frappe.db.set_single_value("Salis Settings", "boarding_notify_max_count", 0)
        )
        self.assertEqual(get_boarding_setting("boarding_notify_max_count"), 5)


    def test_ensure_state_populates_from_manifest_idempotently(self):
        added = boarding_flow.ensure_trip_boarding_state(self.trip.name)
        self.assertEqual(added, 1, "the one manifest worker seeds one state row")
        self.assertEqual(boarding_flow.ensure_trip_boarding_state(self.trip.name), 0)
        row = self._row()
        self.assertIsNotNone(row)
        self.assertEqual(row.status, "Pending")


    def test_wrong_bus_returns_correct_trip_and_driver(self):
        scanned_wrong_trip = "DT-WRONG-" + _h()
        with _patch_masar_resolver(self.trip.name, self.request.name):
            result = boarding_flow.build_wrong_bus_result(scanned_wrong_trip, self.employee.name)

        self.assertIsNotNone(result, "a worker with a real trip gets a correction")
        self.assertTrue(result["wrong_bus"])
        self.assertEqual(result["correct_trip"], self.trip.name)
        self.assertEqual(result["correct_driver"]["name"], self.driver.full_name)
        self.assertEqual(result["correct_driver"]["phone"], "+966500000001")
        hint = frappe.cache.get_value("salis_misboard:" + self.employee.name)
        self.assertIsNotNone(hint)
        self.assertEqual(hint["correct_trip"], self.trip.name)


    def test_notify_caps_at_max_and_depart_marks_absent(self):
        self._seed_state(started_minutes_ago=30)
        max_count = get_boarding_setting("boarding_notify_max_count")
        for _i in range(max_count + 3):
            boarding_flow.notify_remaining_passengers(self.trip.name)
        self.assertEqual(self._row().notify_count, max_count, "notify_count caps at the max")

        result = boarding_flow.depart_and_finalize(self.trip.name)
        self.assertEqual(self._row().status, "Absent")
        self.assertEqual(result["absent"], 1)
        self.assertEqual(result["boarded"], 0)
        log = frappe.db.get_value(
            "Trip Start Log",
            {"dispatch_trip": self.trip.name},
            ["status", "end_datetime"],
            as_dict=True,
        )
        self.assertEqual(log.status, "Completed", "depart closes the manifest log")
        self.assertIsNotNone(log.end_datetime, "depart stamps the log end time")

    def test_depart_before_grace_marks_no_one_absent(self):
        self._seed_state(started_minutes_ago=0)
        for _i in range(get_boarding_setting("boarding_notify_max_count") + 2):
            boarding_flow.notify_remaining_passengers(self.trip.name)
        result = boarding_flow.depart_and_finalize(self.trip.name)
        self.assertEqual(result["absent"], 0, "no absence before the grace window elapses")
        self.assertEqual(self._row().status, "Pending")


    def test_get_trip_boarding_is_side_effect_free(self):
        self._seed_state(started_minutes_ago=30)
        before = self._row().notify_count
        result = boarding_flow.get_trip_boarding(self.trip.name)
        after = self._row().notify_count
        self.assertEqual(before, after, "a read must not bump notify_count")
        self.assertEqual(after, 0, "a read leaves notify_count at 0")
        self.assertEqual(
            result["worker_wait_request_max"], get_boarding_setting("worker_wait_request_max")
        )
        self.assertEqual(
            result["worker_wait_request_seconds"],
            get_boarding_setting("worker_wait_request_seconds"),
        )
        self.assertEqual(result["workers"][0]["employee"], self.employee.name)

    def test_get_trip_boarding_reflects_self_confirmed_worker(self):
        self._seed_state()
        with _patch_masar_resolver(self.trip.name, self.request.name):
            boarding_flow.worker_claim_boarded(token="t")
        result = boarding_flow.get_trip_boarding(self.trip.name)
        worker = next(w for w in result["workers"] if w["employee"] == self.employee.name)
        self.assertEqual(worker["status"], "Boarded", "the self-confirm boards immediately")
        self.assertEqual(worker["confirm_source"], "Worker")


    def test_worker_request_wait_caps_at_max(self):
        self._seed_state()
        max_count = get_boarding_setting("worker_wait_request_max")
        with _patch_masar_resolver(self.trip.name, self.request.name):
            last = None
            for _i in range(max_count + 3):
                last = boarding_flow.worker_request_wait(token="t")
        self.assertEqual(last["wait_count"], max_count, "wait_count caps at the max")
        self.assertEqual(last["remaining"], 0)
        self.assertEqual(self._row().wait_count, max_count)


    def _boarding_events(self):
        """The registered boarding-event workers on the trip's open manifest log."""
        log = frappe.db.get_value(
            "Trip Start Log", {"dispatch_trip": self.trip.name, "docstatus": 0}, "name"
        )
        if not log:
            return []
        return frappe.get_all(
            "Trip Boarding Event",
            filters={"parent": log, "parenttype": "Trip Start Log", "is_unregistered": 0},
            pluck="worker",
        )

    def test_worker_claim_self_confirms_and_records_event(self):
        self._seed_state()
        with _patch_masar_resolver(self.trip.name, self.request.name):
            claim = boarding_flow.worker_claim_boarded(token="t")
        self.assertEqual(claim["status"], "Boarded")
        self.assertEqual(claim["confirm_source"], "Worker")
        self.assertEqual(self._row().status, "Boarded")
        self.assertEqual(self._row().confirm_source, "Worker")
        self.assertIn(self.employee.name, self._boarding_events(), "the manifest records the event")

    def test_worker_claim_is_idempotent(self):
        self._seed_state()
        with _patch_masar_resolver(self.trip.name, self.request.name):
            boarding_flow.worker_claim_boarded(token="t")
            boarding_flow.worker_claim_boarded(token="t")
        self.assertEqual(self._row().status, "Boarded")
        self.assertEqual(
            self._boarding_events().count(self.employee.name), 1, "no duplicate boarding event"
        )

    def test_worker_claim_names_the_trip_dispatch_trip_on_every_return(self):
        """One key name for the trip on all three paths, so the two no-ops are
        distinguishable.

        The endpoint answers ``dispatch_trip`` on every path — both no-ops and
        success — under one key name. Answering ``trip`` on the no-ops instead would
        leave a SPA reading ``result.dispatch_trip`` seeing ``undefined``, unable to
        tell "no boardable trip today" from "not on this trip's manifest" — the
        second of which carries a REAL trip id. Both no-ops are asserted here because
        they differ in exactly that value: None versus the resolved trip.
        """
        from apex.salis.api import masar

        self._seed_state()

        # No boardable trip today: the forward resolver finds nothing.
        with patch.object(masar, "_resolve_worker", return_value=self.employee.name), \
                patch.object(masar, "_worker_today_dispatch_trip", return_value=None):
            no_trip = boarding_flow.worker_claim_boarded(token="t")

        # Resolved onto a real trip, but this worker is not on its manifest, so
        # ensure_trip_boarding_state seeds no row for them.
        outsider = frappe.get_doc(
            {"doctype": "Employee", "first_name": "OUT-" + _h(), "naming_series": "HR-EMP-"}
        )
        outsider.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        self._cleanup.append(("Employee", outsider.name))
        with patch.object(masar, "_resolve_worker", return_value=outsider.name), \
                patch.object(
                    masar,
                    "_worker_today_dispatch_trip",
                    return_value=(self.trip.name, self.request.name, "Gate", None),
                ):
            off_manifest = boarding_flow.worker_claim_boarded(token="t")

        with _patch_masar_resolver(self.trip.name, self.request.name):
            boarded = boarding_flow.worker_claim_boarded(token="t")

        # one key name everywhere -- the regression is `trip` coming back.
        for label, result in (
            ("no-trip", no_trip), ("not-on-manifest", off_manifest), ("boarded", boarded)
        ):
            self.assertIn("dispatch_trip", result, f"the {label} return must name the trip dispatch_trip")
            self.assertNotIn("trip", result, f"the {label} return must not resurrect the `trip` key")

        # The two no-ops are told apart by the trip value, not by a missing key.
        self.assertIsNone(no_trip["dispatch_trip"], "no boardable trip resolves to None")
        self.assertIsNone(no_trip["status"])
        self.assertEqual(
            off_manifest["dispatch_trip"],
            self.trip.name,
            "not-on-manifest carries the REAL trip it resolved onto",
        )
        self.assertIsNone(off_manifest["status"], "not-on-manifest boards nobody")
        self.assertEqual(boarded["dispatch_trip"], self.trip.name)
        self.assertEqual(boarded["status"], "Boarded")

    def test_driver_mark_not_boarded_reverses_self_confirm(self):
        self._seed_state()
        with _patch_masar_resolver(self.trip.name, self.request.name):
            boarding_flow.worker_claim_boarded(token="t")
        self.assertIn(self.employee.name, self._boarding_events())

        result = boarding_flow.driver_mark_not_boarded(self.trip.name, self.employee.name)
        self.assertEqual(result["status"], "Pending")
        self.assertEqual(result["reject_count"], 1)
        self.assertEqual(self._row().status, "Pending")
        self.assertIsNone(self._row().confirm_source)
        self.assertNotIn(
            self.employee.name, self._boarding_events(), "the override drops the boarding event"
        )

        with _patch_masar_resolver(self.trip.name, self.request.name):
            reclaim = boarding_flow.worker_claim_boarded(token="t")
        self.assertEqual(reclaim["status"], "Boarded")
        self.assertEqual(self._row().reject_count, 1, "reject_count is preserved across re-confirm")

    def test_worker_poll_reflects_self_confirm(self):
        self._seed_state()
        with _patch_masar_resolver(self.trip.name, self.request.name):
            boarding_flow.worker_claim_boarded(token="t")
            state = boarding_flow.worker_trip_boarding(token="t")
        self.assertEqual(state["status"], "Boarded")
        self.assertEqual(state["confirm_source"], "Worker")


    def _seed_arrival_route(self):
        """Give the trip a Route Plan + one Route Stop on a fresh building, link the
        trip to that plan, and open a Trip Start Log. Returns (building, route_stop,
        log) — the worker's own pickup stop, the join _worker_pickup_arrival keys on."""
        building = frappe.get_doc(
            {"doctype": "Building", "building_name": "TBF-BLD-" + _h()}
        )
        building.flags.ignore_mandatory = True
        building.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        self._cleanup.append(("Building", building.name))

        plan = frappe.get_doc(
            {
                "doctype": "Route Plan",
                "naming_series": "RP-.######",
                "route_name": "TBF-RP-" + _h(),
                "transport_request": self.request.name,
            }
        )
        plan.append(
            "stops", {"stop_name": "Pickup", "accommodation_building": building.name}
        )
        plan.flags.ignore_validate = True
        plan.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        self._cleanup.append(("Route Plan", plan.name))

        # ``_resolve_my_trip`` (apex/salis/api/driver_portal/__init__.py:139-166) only
        # honours a trip whose status is "Dispatched" — the one non-final state the
        # workflow (apex/salis/workflow/dispatch_trip_workflow/dispatch_trip_workflow.json)
        # lets a driver execute against — and whose trip_date is today or yesterday;
        # ``self.trip`` is fixtured on a fixed calendar date the recency check rejects.
        frappe.db.set_value(
            "Dispatch Trip",
            self.trip.name,
            {
                "route_plan": plan.name,
                "status": "Dispatched",
                "trip_date": frappe.utils.today(),
            },
        )
        # ``_resolve_trip_route_stop`` (apex/salis/api/driver_portal/__init__.py:170-203)
        # keys on the Dispatch Trip's OWN copy of the stop, not the Route Plan's row —
        # the same copy ``trip_manifest.copy_route_stops`` makes at Dispatch Trip
        # ``validate`` (apex/salis/doctype/dispatch_trip/trip_manifest.py:93-108).
        # Reusing that helper directly here, rather than a full ``trip.save()``,
        # avoids tripping the unrelated validate-time checks (odometer, vehicle
        # compliance, capacity) this minimal fixture never satisfies.
        from apex.salis.doctype.dispatch_trip.trip_manifest import copy_route_stops

        trip_doc = frappe.get_doc("Dispatch Trip", self.trip.name)
        copy_route_stops(trip_doc)
        trip_doc.flags.ignore_validate = True
        trip_doc.save(ignore_permissions=True)
        route_stop = frappe.db.get_value(
            "Route Stop",
            {
                "parent": self.trip.name,
                "parenttype": "Dispatch Trip",
                "accommodation_building": building.name,
            },
            "name",
        )
        log = frappe.get_doc(
            {
                "doctype": "Trip Start Log",
                "dispatch_trip": self.trip.name,
                "driver": self.driver.name,
                "route_plan": plan.name,
                "status": "Started",
                "start_datetime": now_datetime(),
            }
        )
        log.insert(ignore_permissions=True)
        return building.name, route_stop, log.name

    def test_driver_arrival_publishes_and_reaches_worker_poll(self):
        building, route_stop, _log = self._seed_arrival_route()
        boarding_flow.ensure_trip_boarding_state(self.trip.name)

        from apex.salis.api import driver_portal

        frappe.db.set_single_value("Salis Settings", "enable_driver_portal", 1)
        self.addCleanup(
            lambda: frappe.db.set_single_value("Salis Settings", "enable_driver_portal", 0)
        )

        # mark_arrived is defined in execution.py (split from this god module per
        # its own docstring, apex/salis/api/driver_portal/execution.py:1-8) and
        # resolves its own module-global ``_resolve_driver``, so the patch target
        # is ``execution``, not the ``driver_portal`` package it is re-exported into.
        with patch.object(execution, "_resolve_driver", return_value=self.driver.name), patch(
            "frappe.publish_realtime"
        ) as pub:
            # mark_arrived(dispatch_trip, route_stop) always marks arrival — there is
            # no ``arrived`` toggle on the endpoint (apex/salis/api/driver_portal/execution.py:191-234).
            driver_portal.mark_arrived(self.trip.name, route_stop)

        arrival_calls = [
            c for c in pub.call_args_list if c.args and c.args[0] == "boarding_arrived"
        ]
        self.assertEqual(len(arrival_calls), 1, "mark_arrived publishes one boarding_arrived event")
        kwargs = arrival_calls[0].kwargs
        self.assertEqual(kwargs.get("doctype"), "Dispatch Trip")
        self.assertTrue(kwargs.get("after_commit"), "arrival must publish after_commit")
        self.assertEqual(arrival_calls[0].args[1].get("dispatch_trip"), self.trip.name)
        self.assertEqual(arrival_calls[0].args[1].get("route_stop"), route_stop)

        self.assertTrue(
            frappe.db.get_value(
                "Trip Stop Progress", {"route_stop": route_stop, "arrived": 1}, "name"
            ),
            "the arrival flag is persisted on the stop-progress rail",
        )

        with _patch_masar_resolver(self.trip.name, self.request.name, building=building):
            state = boarding_flow.worker_trip_boarding(token="t")
        self.assertIsNotNone(state.get("driver_arrived"), "the worker poll delivers the arrival")
        self.assertTrue(state["driver_arrived"]["arrived"])

    def test_driver_cannot_mark_a_route_stop_from_another_plan(self):
        _building, _route_stop, log_name = self._seed_arrival_route()
        foreign_plan = frappe.get_doc(
            {
                "doctype": "Route Plan",
                "naming_series": "RP-.######",
                "route_name": "TBF-FOREIGN-" + _h(),
            }
        )
        foreign_plan.append("stops", {"stop_name": "Forged Stop"})
        foreign_plan.flags.ignore_validate = True
        foreign_plan.insert(
            ignore_permissions=True,
            ignore_links=True,
            ignore_mandatory=True,
        )
        self._cleanup.append(("Route Plan", foreign_plan.name))
        foreign_stop = frappe.db.get_value(
            "Route Stop",
            {"parent": foreign_plan.name, "parenttype": "Route Plan"},
            "name",
        )

        from apex.salis.api import driver_portal

        frappe.db.set_single_value("Salis Settings", "enable_driver_portal", 1)
        with patch.object(
            execution, "_resolve_driver", return_value=self.driver.name
        ), self.assertRaises(frappe.PermissionError):
            # mark_arrived(dispatch_trip, route_stop) takes no sequence/stop_name —
            # those are derived from the resolved stop, never the caller
            # (apex/salis/api/driver_portal/execution.py:191-234). Patched on
            # ``execution``, the module its own ``_resolve_driver`` lookup resolves
            # against (apex/salis/api/driver_portal/execution.py:14-21).
            driver_portal.mark_arrived(self.trip.name, foreign_stop)

        with patch.object(
            execution, "_resolve_driver", return_value=self.driver.name
        ), self.assertRaises(frappe.PermissionError):
            execution.mark_stop_progress(
                self.trip.name,
                foreign_stop,
                done=1,
                sequence=999,
                stop_name="Forged Stop",
            )

        self.assertEqual(
            frappe.db.count("Trip Stop Progress", {"parent": log_name}),
            0,
        )

    def test_stop_progress_derives_sequence_and_name_from_owned_route_stop(self):
        _building, route_stop, log_name = self._seed_arrival_route()
        frappe.db.set_single_value("Salis Settings", "enable_driver_portal", 1)
        with patch.object(
            execution, "_resolve_driver", return_value=self.driver.name
        ):
            execution.mark_stop_progress(
                self.trip.name,
                route_stop,
                done=1,
                sequence=999,
                stop_name="Forged Stop",
            )

        progress = frappe.db.get_value(
            "Trip Stop Progress",
            {"parent": log_name, "route_stop": route_stop},
            ["sequence", "stop_name"],
            as_dict=True,
        )
        self.assertEqual(progress.sequence, 1)
        self.assertEqual(progress.stop_name, "Pickup")

    def test_worker_poll_silent_before_arrival(self):
        building, _route_stop, _log = self._seed_arrival_route()
        boarding_flow.ensure_trip_boarding_state(self.trip.name)
        with _patch_masar_resolver(self.trip.name, self.request.name, building=building):
            state = boarding_flow.worker_trip_boarding(token="t")
        self.assertIsNone(state.get("driver_arrived"), "no arrival signal before the driver marks it")


class _patch_masar_resolver:
    """Patch masar._resolve_worker + _worker_today_dispatch_trip (the identity +
    forward-trip resolvers the token-scoped endpoints + wrong-bus use) so a test
    need not provision a Masar Worker Token. Patches them where boarding_flow
    imports them (function-local imports), i.e. on the masar module itself."""

    def __init__(self, dispatch_trip, transport_request, building=None):
        self.dispatch_trip = dispatch_trip
        self.transport_request = transport_request
        self.building = building
        self._patches = []

    def __enter__(self):
        from apex.salis.api import masar

        target = frappe.db.get_value(
            "Transport Request Worker",
            {"parent": self.transport_request},
            "employee",
        )

        p1 = patch.object(masar, "_resolve_worker", return_value=target)
        p2 = patch.object(
            masar,
            "_worker_today_dispatch_trip",
            return_value=(self.dispatch_trip, self.transport_request, "Gate", self.building),
        )
        self._patches = [p1, p2]
        for p in self._patches:
            p.start()
        return self

    def __exit__(self, *exc):
        for p in self._patches:
            p.stop()
        return False
