# Copyright (c) 2026, AFMCO and contributors
"""Masar worker trip rating — submit_trip_rating (salis/api/masar.py).

The shipped endpoint gated "was the worker on this trip?" with a flat filter on
``Passenger Manifest`` for a ``{dispatch_trip, employee}`` pair — but Passenger
Manifest has no ``employee`` column (its passengers live on the child ``Manifest
Passenger``), so every call raised on a non-existent column: the feature was
dead-on-arrival. The membership is now resolved through the trip's Transport
Request worker manifest (the same demand->worker chain get_worker_transport
uses) or the Passenger Manifest child rows.

A rating is about a ride that happened, so the endpoint refuses any trip whose
Dispatch Trip status is not ``Completed``; the fixtures below build the trip and
then land it on that status (a Dispatch Trip must be inserted ``Planned``, so
``make_worker_trip`` writes the target status afterwards).

These cases prove the goal + the fail-closed contract on a migrated site with no
production data:
  * a worker on the trip submits a rating -> success, exactly one row, scoped to
    that worker (the goal);
  * a worker who was NOT on the trip is refused (PermissionError) — no row;
  * a second rating of the same trip by the same worker is refused — still one
    row (idempotent-by-rejection);
  * an out-of-range star count (0 or 6) is refused before any write;
  * a blank token fails closed (PermissionError) before anything is considered.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.salis.api import masar
from apex.tests.factories import (
    WorkerTripMixin as _WorkerTripMixin,
    make_masar_building as _building,
    make_project as _project,
    make_test_driver as _ensure_test_driver,
    make_worker_employee as _employee,
)
from apex.tests.factories import ensure_worker_token


class TestMasarTripRating(_WorkerTripMixin, FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.project = _project("Masar TR Project")
        cls.building = _building("Masar TR Building")
        cls.driver = _ensure_test_driver()

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        if frappe.db.exists("Building", cls.building):
            frappe.delete_doc("Building", cls.building, ignore_permissions=True, force=True)
        if frappe.db.exists("Project", cls.project):
            frappe.delete_doc("Project", cls.project, ignore_permissions=True, force=True)
        frappe.db.commit()
        super().tearDownClass()

    def setUp(self):
        frappe.set_user("Administrator")

    def tearDown(self):
        frappe.set_user("Administrator")

    def _worker(self, suffix):
        """A worker unique to THIS test method, so a rating written in one test
        never bleeds into another."""
        return _employee(f"Masar TR {self._testMethodName} {suffix}")

    def _mark_boarded(self, dispatch_trip, *employees):
        """Land the trip's ``Trip Boarding State`` rows for ``employees`` on
        ``Boarded``.

        Inserting a Dispatch Trip seeds one boarding row per manifest worker at
        ``Pending`` (trip_manifest.sync_passengers). Where a trip carries boarding
        rows at all, ``_worker_was_on_trip`` treats them as authoritative and only
        a ``Boarded`` row counts as having ridden — so a rider fixture has to say
        the worker actually boarded, not merely that they were manifested."""
        for employee in employees:
            row = frappe.db.get_value(
                "Trip Boarding State",
                {
                    "parent": dispatch_trip,
                    "parenttype": "Dispatch Trip",
                    "employee": employee,
                },
                "name",
            )
            frappe.db.set_value("Trip Boarding State", row, "status", "Boarded")

    def _purge_ratings(self, dispatch_trip):
        """Drop any Transport Trip Rating the endpoint wrote for a trip — the
        trip-mixin cleanup removes the Dispatch Trip but not these ratings."""
        frappe.set_user("Administrator")
        for name in frappe.get_all(
            "Transport Trip Rating", filters={"dispatch_trip": dispatch_trip}, pluck="name"
        ):
            frappe.delete_doc(
                "Transport Trip Rating", name, ignore_permissions=True, force=True
            )

    def _ratings_for(self, dispatch_trip, employee):
        return frappe.get_all(
            "Transport Trip Rating",
            filters={"dispatch_trip": dispatch_trip, "employee": employee},
            fields=["name", "rating", "feedback"],
        )

    def test_worker_on_trip_can_rate(self):
        """The goal: a tokenized worker who rode the trip submits a rating ->
        success, exactly one row, scoped to that worker."""
        w1 = self._worker("a")
        w2 = self._worker("b")
        tr, rp, dt = self._worker_trip(
            self.driver, self.project, self.building, [w1, w2], "TR Route A",
            status="Completed",
        )
        self._mark_boarded(dt.name, w1, w2)
        self.addCleanup(lambda: self._purge_ratings(dt.name))
        token = ensure_worker_token(w1)
        self.assertEqual(self._ratings_for(dt.name, w1), [])

        res = masar.submit_trip_rating(
            token=token,
            dispatch_trip=dt.name,
            rating=5,
            feedback="Great ride",
            transport_request=tr.name,
        )
        self.assertEqual(res["status"], "success")

        rows = self._ratings_for(dt.name, w1)
        self.assertEqual(len(rows), 1, "exactly one rating for this worker")
        self.assertTrue(rows[0]["rating"], "the star count was persisted")
        self.assertEqual(rows[0]["feedback"], "Great ride")
        self.assertEqual(self._ratings_for(dt.name, w2), [])

    def test_worker_not_on_trip_is_rejected(self):
        """A worker who was NOT on the trip cannot rate it — the on-trip gate is
        resolved through the trip's request/manifest, and fails closed."""
        on = self._worker("on")
        off = self._worker("off")
        tr, rp, dt = self._worker_trip(
            self.driver, self.project, self.building, [on], "TR Route B",
            status="Completed",
        )
        self._mark_boarded(dt.name, on)
        self.addCleanup(lambda: self._purge_ratings(dt.name))
        token = ensure_worker_token(off)
        self.assertEqual(masar._resolve_worker(token), off)

        with self.assertRaises(frappe.PermissionError):
            masar.submit_trip_rating(
                token=token, dispatch_trip=dt.name, rating=4, transport_request=tr.name
            )
        self.assertEqual(self._ratings_for(dt.name, off), [], "no row written on reject")

    def test_duplicate_rating_is_rejected(self):
        """A second rating of the same trip by the same worker is refused; the
        first rating remains the only row."""
        w1 = self._worker("a")
        tr, rp, dt = self._worker_trip(
            self.driver, self.project, self.building, [w1], "TR Route C",
            status="Completed",
        )
        self._mark_boarded(dt.name, w1)
        self.addCleanup(lambda: self._purge_ratings(dt.name))
        token = ensure_worker_token(w1)

        first = masar.submit_trip_rating(
            token=token, dispatch_trip=dt.name, rating=5, transport_request=tr.name
        )
        self.assertEqual(first["status"], "success")

        with self.assertRaises(frappe.ValidationError):
            masar.submit_trip_rating(
                token=token, dispatch_trip=dt.name, rating=3, transport_request=tr.name
            )
        self.assertEqual(
            len(self._ratings_for(dt.name, w1)), 1, "duplicate must not add a row"
        )

    def test_out_of_range_rating_is_rejected(self):
        """A star count outside 1..5 is refused before any write, even for a
        worker who was on the trip."""
        w1 = self._worker("a")
        tr, rp, dt = self._worker_trip(
            self.driver, self.project, self.building, [w1], "TR Route D",
            status="Completed",
        )
        self._mark_boarded(dt.name, w1)
        self.addCleanup(lambda: self._purge_ratings(dt.name))
        token = ensure_worker_token(w1)

        for bad in (0, 6):
            with self.assertRaises(frappe.ValidationError):
                masar.submit_trip_rating(
                    token=token,
                    dispatch_trip=dt.name,
                    rating=bad,
                    transport_request=tr.name,
                )
        self.assertEqual(self._ratings_for(dt.name, w1), [], "no row for a bad rating")

    def test_blank_token_is_rejected(self):
        """The write funnels through _resolve_worker, so a blank/missing token
        fails closed (PermissionError) before a rating is considered."""
        for blank in (None, "", "   "):
            with self.assertRaises(frappe.PermissionError):
                masar.submit_trip_rating(token=blank, dispatch_trip="X", rating=5)

