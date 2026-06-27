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
  * Two-sided confirmation: claim -> driver confirm -> Boarded; claim -> driver
    reject -> reject_count++ -> worker re-claim -> Worker Claimed; claim ->
    timeout (backdated claim) -> Auto-confirm Boarded.

The token-scoped worker endpoints resolve identity via masar._resolve_worker and
masar._worker_today_dispatch_trip; the tests patch those two so a real Masar
Worker Token need not be provisioned (the identity contract is exercised
elsewhere). ``test_ignore`` prunes the HR/master auto-dependency walk.
"""

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, now_datetime

from apex_habitat.apex_core.doctype.salis_settings.salis_settings import (
    BOARDING_FLOW_DEFAULTS,
    get_boarding_setting,
    get_boarding_settings,
)
from apex_habitat.salis.api import boarding_flow

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


def _h(n=6):
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

    # helpers

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

    # settings fallback

    def test_settings_fall_back_to_defaults_when_zero_or_unset(self):
        # A fresh Single stores 0 for the new Ints; the accessor must coalesce to
        # the built-in default, never the stored 0.
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

    # populate

    def test_ensure_state_populates_from_manifest_idempotently(self):
        added = boarding_flow.ensure_trip_boarding_state(self.trip.name)
        self.assertEqual(added, 1, "the one manifest worker seeds one state row")
        # Re-run adds nothing.
        self.assertEqual(boarding_flow.ensure_trip_boarding_state(self.trip.name), 0)
        row = self._row()
        self.assertIsNotNone(row)
        self.assertEqual(row.status, "Pending")

    # Feature A: wrong bus

    def test_wrong_bus_returns_correct_trip_and_driver(self):
        # The scanned (wrong) trip is a DIFFERENT trip; the worker's REAL trip is
        # self.trip (their manifest). _worker_today_dispatch_trip is the forward
        # resolver build_wrong_bus_result uses.
        scanned_wrong_trip = "DT-WRONG-" + _h()
        with _patch_masar_resolver(self.trip.name, self.request.name):
            result = boarding_flow.build_wrong_bus_result(scanned_wrong_trip, self.employee.name)

        self.assertIsNotNone(result, "a worker with a real trip gets a correction")
        self.assertTrue(result["wrong_bus"])
        self.assertEqual(result["correct_trip"], self.trip.name)
        self.assertEqual(result["correct_driver"]["name"], self.driver.full_name)
        self.assertEqual(result["correct_driver"]["phone"], "+966500000001")
        # The transient misboard hint is readable by the worker poll.
        hint = frappe.cache.get_value("salis_misboard:" + self.employee.name)
        self.assertIsNotNone(hint)
        self.assertEqual(hint["correct_trip"], self.trip.name)

    # Feature B: notify caps + absent at depart

    def test_notify_caps_at_max_and_depart_marks_absent(self):
        self._seed_state(started_minutes_ago=30)  # well past grace
        max_count = get_boarding_setting("boarding_notify_max_count")
        # Bump past the cap; notify_count must never exceed the max.
        for _i in range(max_count + 3):
            boarding_flow.notify_remaining_passengers(self.trip.name)
        self.assertEqual(self._row().notify_count, max_count, "notify_count caps at the max")

        # Depart: the exhausted-notify Pending worker becomes Absent.
        result = boarding_flow.depart_and_finalize(self.trip.name)
        self.assertEqual(self._row().status, "Absent")
        self.assertEqual(result["absent"], 1)
        self.assertEqual(result["boarded"], 0)
        # The manifest log is closed (status -> Completed, end stamped).
        log = frappe.db.get_value(
            "Trip Start Log",
            {"dispatch_trip": self.trip.name},
            ["status", "end_datetime"],
            as_dict=True,
        )
        self.assertEqual(log.status, "Completed", "depart closes the manifest log")
        self.assertIsNotNone(log.end_datetime, "depart stamps the log end time")

    def test_depart_before_grace_marks_no_one_absent(self):
        self._seed_state(started_minutes_ago=0)  # within grace
        for _i in range(get_boarding_setting("boarding_notify_max_count") + 2):
            boarding_flow.notify_remaining_passengers(self.trip.name)
        result = boarding_flow.depart_and_finalize(self.trip.name)
        self.assertEqual(result["absent"], 0, "no absence before the grace window elapses")
        self.assertEqual(self._row().status, "Pending")

    # pure read: get_trip_boarding has no side effects

    def test_get_trip_boarding_is_side_effect_free(self):
        self._seed_state(started_minutes_ago=30)  # past grace, so notify WOULD bump
        before = self._row().notify_count
        result = boarding_flow.get_trip_boarding(self.trip.name)
        after = self._row().notify_count
        self.assertEqual(before, after, "a read must not bump notify_count")
        self.assertEqual(after, 0, "a read leaves notify_count at 0")
        # Same per-worker shape as notify, plus the wait settings the driver needs.
        self.assertEqual(
            result["worker_wait_request_max"], get_boarding_setting("worker_wait_request_max")
        )
        self.assertEqual(
            result["worker_wait_request_seconds"],
            get_boarding_setting("worker_wait_request_seconds"),
        )
        self.assertEqual(result["workers"][0]["employee"], self.employee.name)

    def test_get_trip_boarding_reflects_auto_confirmed_claim(self):
        self._seed_state()
        with _patch_masar_resolver(self.trip.name, self.request.name):
            boarding_flow.worker_claim_boarded(token="t")
        minutes = get_boarding_setting("boarding_auto_confirm_minutes")
        frappe.db.set_value(
            "Trip Boarding State",
            self._row().name,
            "worker_claim_at",
            add_to_date(now_datetime(), minutes=-(minutes + 1)),
            update_modified=False,
        )
        result = boarding_flow.get_trip_boarding(self.trip.name)
        worker = next(w for w in result["workers"] if w["employee"] == self.employee.name)
        self.assertEqual(worker["status"], "Boarded", "read applies the auto-confirm timeout")
        self.assertEqual(worker["confirm_source"], "Auto")

    # Feature B: worker wait caps

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

    # two-sided confirmation

    def test_claim_then_driver_confirm_boards(self):
        self._seed_state()
        with _patch_masar_resolver(self.trip.name, self.request.name):
            claim = boarding_flow.worker_claim_boarded(token="t")
        self.assertEqual(claim["status"], "Worker Claimed")
        self.assertIsNotNone(self._row().worker_claim_at)

        result = boarding_flow.driver_confirm_boarding(
            self.trip.name, self.employee.name, "confirm"
        )
        self.assertEqual(result["status"], "Boarded")
        self.assertEqual(result["confirm_source"], "Driver")
        self.assertEqual(self._row().status, "Boarded")

    def test_claim_reject_reclaim_cycle(self):
        self._seed_state()
        with _patch_masar_resolver(self.trip.name, self.request.name):
            boarding_flow.worker_claim_boarded(token="t")
            rej = boarding_flow.driver_confirm_boarding(
                self.trip.name, self.employee.name, "reject"
            )
            self.assertEqual(rej["status"], "Driver Rejected")
            self.assertEqual(rej["reject_count"], 1)
            self.assertEqual(self._row().status, "Driver Rejected")

            # Worker re-asserts: Driver Rejected -> Worker Claimed, count preserved.
            reclaim = boarding_flow.worker_claim_boarded(token="t")
        self.assertEqual(reclaim["status"], "Worker Claimed")
        self.assertEqual(self._row().reject_count, 1, "reject_count is preserved across re-claim")

    def test_claim_timeout_auto_confirms(self):
        self._seed_state()
        with _patch_masar_resolver(self.trip.name, self.request.name):
            boarding_flow.worker_claim_boarded(token="t")
        # Backdate the claim past the auto-confirm window.
        minutes = get_boarding_setting("boarding_auto_confirm_minutes")
        frappe.db.set_value(
            "Trip Boarding State",
            self._row().name,
            "worker_claim_at",
            add_to_date(now_datetime(), minutes=-(minutes + 1)),
            update_modified=False,
        )
        # Read-time auto-confirm (worker poll) flips it to Boarded/Auto.
        with _patch_masar_resolver(self.trip.name, self.request.name):
            state = boarding_flow.worker_trip_boarding(token="t")
        self.assertEqual(state["status"], "Boarded")
        self.assertEqual(state["confirm_source"], "Auto")
        self.assertEqual(self._row().status, "Boarded")

    def test_scheduled_tick_auto_confirms_without_a_read_path(self):
        self._seed_state()
        with _patch_masar_resolver(self.trip.name, self.request.name):
            boarding_flow.worker_claim_boarded(token="t")
        minutes = get_boarding_setting("boarding_auto_confirm_minutes")
        frappe.db.set_value(
            "Trip Boarding State",
            self._row().name,
            "worker_claim_at",
            add_to_date(now_datetime(), minutes=-(minutes + 1)),
            update_modified=False,
        )
        confirmed = boarding_flow.auto_confirm_claimed_boardings()
        self.assertGreaterEqual(confirmed, 1)
        self.assertEqual(self._row().status, "Boarded")
        self.assertEqual(self._row().confirm_source, "Auto")

    def test_worker_poll_returns_rejection_state(self):
        self._seed_state()
        with _patch_masar_resolver(self.trip.name, self.request.name):
            boarding_flow.worker_claim_boarded(token="t")
            boarding_flow.driver_confirm_boarding(self.trip.name, self.employee.name, "reject")
            state = boarding_flow.worker_trip_boarding(token="t")
        self.assertEqual(state["status"], "Driver Rejected")
        self.assertEqual(state["reject_count"], 1)


class _patch_masar_resolver:
    """Patch masar._resolve_worker + _worker_today_dispatch_trip (the identity +
    forward-trip resolvers the token-scoped endpoints + wrong-bus use) so a test
    need not provision a Masar Worker Token. Patches them where boarding_flow
    imports them (function-local imports), i.e. on the masar module itself."""

    def __init__(self, dispatch_trip, transport_request):
        self.dispatch_trip = dispatch_trip
        self.transport_request = transport_request
        self._patches = []

    def __enter__(self):
        from apex_habitat.salis.api import masar

        # Resolve to THE test employee — the setUp's single manifest worker.
        target = frappe.db.get_value(
            "Transport Request Worker",
            {"parent": self.transport_request},
            "employee",
        )

        p1 = patch.object(masar, "_resolve_worker", return_value=target)
        p2 = patch.object(
            masar,
            "_worker_today_dispatch_trip",
            return_value=(self.dispatch_trip, self.transport_request, "Gate", None),
        )
        self._patches = [p1, p2]
        for p in self._patches:
            p.start()
        return self

    def __exit__(self, *exc):
        for p in self._patches:
            p.stop()
        return False
