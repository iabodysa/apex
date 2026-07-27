# Copyright (c) 2026, AFMCO and contributors
"""Worker self-confirm boarding must take the same trip row lock the driver scan takes.

``worker_claim_boarded`` get-or-creates the trip's draft Trip Start Log, checks
whether the worker is already aboard, then appends a boarding event. That is a
read-modify-write: two simultaneous claims for one (trip, worker) both read "no
open log / not aboard" and each writes, leaving two Trip Start Logs and two Trip
Boarding Events. The driver scan path closed this window with a
``SELECT ... FOR UPDATE`` on the Dispatch Trip row before its get-or-create; this
path did not, so the two paths disagreed about the same invariant.

Two halves:

  1. Structural guard (AST, no site): the Dispatch Trip ``for_update`` lock
     precedes the get-or-create inside each boarding write path covered here, so
     the race window cannot be reopened by a later edit. ``scan_boarding_pass`` is
     deliberately absent — test_boarding_race.py already guards it, and a second
     copy of that assertion would be pure duplication.
  2. Behavioural halves (site): one log and one boarding row survive a repeat
     claim, and a claim that runs in its own connection AFTER a committed winner
     merges onto it instead of writing a second row.

Honest limit on the behavioural halves: both drive the two calls in sequence, the
winner committing before the loser starts, so they are a SEQUENCING
APPROXIMATION, not true interleaving. What makes the sequential result carry over
to genuine concurrency is the InnoDB row lock itself, and that this exact
Dispatch Trip row lock really does block a second live transaction is proven by
test_boarding_race.test_concurrent_scan_lock_blocks_second_connection. The
structural guard above is what ties this path to that lock.

Not covered here: ``masar.confirm_boarding`` has the same unguarded
read-modify-write and still needs the same one-line lock. It is omitted because
salis/api/masar.py sits outside this change's write scope, not because it is safe.
"""

from __future__ import annotations

import unittest

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.salis.api import boarding_flow
from apex.salis.api.driver_portal import boarding as driver_boarding
from apex.tests.factories import WorkerTripMixin
from apex.tests.source_tree import func_source

# (module, function, the get-or-create call the lock must precede)
LOCK_BEFORE_GET_OR_CREATE = [
    (boarding_flow, "worker_claim_boarded", "_get_or_create_trip_log("),
    (driver_boarding, "manual_board_workers", "_get_or_create_log("),
]


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


class TestBoardingWritePathsLockTheTrip(unittest.TestCase):
    """Site-free: reads the source, so it runs anywhere the app imports."""

    def test_lock_precedes_get_or_create_in_every_covered_write_path(self):
        for module, fname, create_call in LOCK_BEFORE_GET_OR_CREATE:
            with self.subTest(function=fname):
                path = module.__file__
                body = func_source(_read(path), path, fname)

                lock_line = next(
                    (
                        ln
                        for ln in body.splitlines()
                        if 'get_value("Dispatch Trip"' in ln and "for_update=True" in ln
                    ),
                    None,
                )
                self.assertIsNotNone(
                    lock_line,
                    f"{fname} must take a for_update lock on the Dispatch Trip row "
                    f"before it get-or-creates the trip log, or two concurrent "
                    f"callers double-board the worker",
                )

                lock_pos = body.find('get_value("Dispatch Trip"')
                create_pos = body.find(create_call)
                self.assertGreater(create_pos, -1, f"{create_call} not found in {fname}")
                self.assertLess(
                    lock_pos,
                    create_pos,
                    f"the Dispatch Trip lock must precede {create_call} in {fname} "
                    f"(race window reopened?)",
                )


class TestWorkerClaimBoardedIsSingleRow(WorkerTripMixin, FrappeTestCase):
    """Site-bound: proves the invariant the lock exists to hold."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        from apex.tests.factories import (
            make_masar_building,
            make_project,
            make_test_driver,
        )

        cls.project = make_project("Worker Claim Race Project")
        cls.building = make_masar_building("Worker Claim Race Building")
        cls.driver = make_test_driver()

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        if frappe.db.exists("Project", cls.project):
            frappe.delete_doc("Project", cls.project, ignore_permissions=True, force=True)
        frappe.db.commit()
        super().tearDownClass()

    def setUp(self):
        frappe.set_user("Administrator")

    def tearDown(self):
        frappe.set_user("Administrator")

    def _purge_trip_logs(self, dispatch_trip):
        """The trip fixture cleans up the Dispatch Trip but not the Trip Start Log
        this endpoint opens."""
        frappe.set_user("Administrator")
        for name in frappe.get_all(
            "Trip Start Log", filters={"dispatch_trip": dispatch_trip}, pluck="name"
        ):
            frappe.db.set_value("Trip Start Log", name, "docstatus", 0, update_modified=False)
            frappe.delete_doc("Trip Start Log", name, ignore_permissions=True, force=True)

    def _fixture(self, route):
        from apex.tests.factories import ensure_worker_token, make_worker_employee

        worker = make_worker_employee(f"Worker Claim Race {self._testMethodName}")
        tr, _rp, dt = self._worker_trip(
            self.driver, self.project, self.building, [worker], route
        )
        self.addCleanup(lambda: self._purge_trip_logs(dt.name))
        return worker, dt, ensure_worker_token(worker)

    def _counts(self, dispatch_trip, worker):
        """The card's two numbers: open logs for the trip, boarding rows for the worker."""
        logs = frappe.get_all(
            "Trip Start Log",
            filters={"dispatch_trip": dispatch_trip, "docstatus": 0},
            pluck="name",
        )
        events = (
            frappe.db.count(
                "Trip Boarding Event",
                {"parent": logs[0], "parenttype": "Trip Start Log", "worker": worker},
            )
            if logs
            else 0
        )
        return len(logs), events

    def test_repeat_claim_leaves_one_log_and_one_boarding_row(self):
        worker, dt, token = self._fixture("Worker Claim Race A")

        first = boarding_flow.worker_claim_boarded(token=token)
        self.assertEqual(first["status"], "Boarded")
        boarding_flow.worker_claim_boarded(token=token)

        logs, events = self._counts(dt.name, worker)
        self.assertEqual(logs, 1, "a repeat claim must not open a second Trip Start Log")
        self.assertEqual(events, 1, "a repeat claim must not append a second boarding event")

    def test_second_connection_claim_merges_onto_the_committed_winner(self):
        """A claim in its OWN transaction, after a committed winner, writes nothing new.

        The serialized loser's path across two real connections: it takes the
        now-free Dispatch Trip lock, re-reads the committed boarding under it, and
        finds the worker already aboard.
        """
        worker, dt, token = self._fixture("Worker Claim Race B")

        with self.primary_connection():
            boarding_flow.worker_claim_boarded(token=token)
            frappe.db.commit()

        logs_after_winner, events_after_winner = self._counts(dt.name, worker)
        self.assertEqual(logs_after_winner, 1)
        self.assertEqual(events_after_winner, 1)

        with self.secondary_connection():
            boarding_flow.worker_claim_boarded(token=token)
            frappe.db.commit()

        logs, events = self._counts(dt.name, worker)
        self.assertEqual(logs, 1, "the loser claim must NOT open a second Trip Start Log")
        self.assertEqual(events, 1, "the loser claim must NOT append a second boarding event")
