# Copyright (c) 2026, AFMCO and contributors
"""Worker self-confirm boarding must take the same trip row lock the driver scan takes.

A worker can self-confirm through TWO endpoints — ``boarding_flow.worker_claim_boarded``
and ``masar.confirm_boarding``. Each get-or-creates the trip's draft Trip Start Log,
checks whether the worker is already aboard, then appends a boarding event. That is a
read-modify-write: two simultaneous confirms for one (trip, worker) both read "no
open log / not aboard" and each writes, leaving two Trip Start Logs and two Trip
Boarding Events. The driver scan path closed this window with a
``SELECT ... FOR UPDATE`` on the Dispatch Trip row before its get-or-create; the
self-confirm paths did not, so the paths disagreed about the same invariant.

Three layers:

  1. Structural guard (AST, no site): the Dispatch Trip ``for_update`` lock
     precedes the get-or-create inside each boarding write path covered here, so
     the race window cannot be reopened by a later edit. ``scan_boarding_pass`` is
     deliberately absent — test_boarding_race.py already guards it, and a second
     copy of that assertion would be pure duplication.
  2. Contention (site, two live connections, BOTH self-confirm endpoints): while
     the endpoint sits mid-flight and UNCOMMITTED on connection A, connection B's
     locking read of the same Dispatch Trip row is rejected. Real cross-transaction
     contention, and it proves the ENDPOINT ITSELF holds the row across its whole
     critical section — not merely that a hand-taken lock contends. One shared body
     runs against each endpoint, so neither can gain the layer without the other.
  3. Behavioural (site): one log and one boarding row survive a repeat confirm, and
     a confirm that runs in its own connection AFTER a committed winner merges onto
     it instead of writing a second row.

Honest limit on layer 3: those tests drive the two calls in sequence, the winner
committing before the loser starts, so they are a SEQUENCING APPROXIMATION, not
true interleaving. They prove the merge-on-re-read OUTCOME; they do not prove the
loser was ever blocked — a layer 3 test still passes with the lock deleted. The
blocking comes from layer 2, now carried by both self-confirm endpoints, and from
test_boarding_race.test_concurrent_scan_lock_blocks_second_connection for the row
lock in general; layer 1 is what ties each path to that lock.

Proven nowhere here: that two confirms dispatched at the same instant interleave in
a particular order. Nothing in this repo forks genuinely simultaneous callers; the
argument is lock primitive plus source structure, not a stress run.

``confirm_boarding``'s SAME-transaction repeat (a plain double-confirm) is not
re-tested here — test_masar_worker_boarding_confirm.test_reconfirm_is_idempotent
already owns it; only the cross-connection halves live in this file.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase, timeout

from apex.salis.api import boarding_flow, masar
from apex.tests.factories import WorkerTripMixin

def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


# The two self-confirm endpoints answer in DIFFERENT shapes — confirm_boarding
# reports ``created``, worker_claim_boarded reports ``status`` — and that is the
# only thing the contention layer needs to differ on. Each adapter runs its own
# endpoint and reports just the Dispatch Trip it resolved; everything after that
# is one shared body, so the two endpoints cannot drift apart in coverage.
def _confirm_boarding_trip(token):
    """Run ``masar.confirm_boarding``; return the Dispatch Trip it resolved."""
    return masar.confirm_boarding(token=token).get("dispatch_trip")


def _worker_claim_trip(token):
    """Run ``boarding_flow.worker_claim_boarded``; return the Dispatch Trip it resolved."""
    return boarding_flow.worker_claim_boarded(token=token).get("dispatch_trip")


class TestSelfConfirmBoardingIsSingleRow(WorkerTripMixin, FrappeTestCase):
    """Site-bound: proves the invariant the lock exists to hold, for BOTH
    self-confirm endpoints (``worker_claim_boarded`` and ``confirm_boarding``)."""

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

    @staticmethod
    def _purge_worker(employee):
        """Best-effort removal of the tagged worker and its token, so a per-run
        Employee does not accumulate. Never raises: a row left on a disposable test
        bench is not worth turning a green test red."""
        frappe.set_user("Administrator")
        token = frappe.db.get_value("Masar Worker Token", {"employee": employee}, "name")
        for doctype, name in (("Masar Worker Token", token), ("Employee", employee)):
            if not name:
                continue
            try:
                frappe.delete_doc(doctype, name, ignore_permissions=True, force=True)
            except Exception:
                # Cleanup must never mask the verdict of the test it follows.
                pass

    def _fixture(self, route):
        """A worker and trip that nothing else can already be holding.

        A random tag (``fixture_tag()``) names the worker, which is the only thing
        that makes it new on every run. ``self._testMethodName`` would be STABLE
        ACROSS RUNS instead, and while ``make_worker_employee`` is get-or-create and
        nothing here ever deletes an Employee, every run would re-adopt the previous
        run's worker together with any Transport Request that run failed to clean up
        — and ``_worker_today_dispatch_trip`` resolves over EVERY today-trip the
        employee is on, breaking ties by ``depart_time asc`` when every fixture
        departs 06:30. A second live request for that worker could then hand back a
        trip that is not this test's, on which they are already aboard, so the
        endpoint would legitimately answer ``created=False``.
        """
        from apex.tests.factories import (
            ensure_worker_token,
            fixture_tag,
            make_worker_employee,
        )

        tag = fixture_tag()
        worker = make_worker_employee(f"Worker Claim Race {tag}")
        # Registered FIRST so it runs LAST (addCleanup is LIFO) — after the trip and
        # request that reference this employee have already been purged.
        self.addCleanup(lambda: self._purge_worker(worker))
        tr, _rp, dt = self._worker_trip(
            self.driver, self.project, self.building, [worker], f"{route} {tag}"
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

    def _assert_live_endpoint_blocks_a_second_connection(self, run_endpoint, route):
        """The genuinely interleaved assertion, run against ONE self-confirm endpoint.

        Connection A runs the real endpoint and does NOT commit, so it is sitting
        inside its own critical section holding the Dispatch Trip row. Connection B —
        standing in for the simultaneous second confirm — takes the same locking read
        with ``wait=False`` and is rejected (QueryTimeoutError). That is the
        endpoint's own transaction contending, so a second confirm cannot reach
        ``_get_or_create_trip_log`` / ``_already_boarded`` on a stale read while the
        first is mid-write.

        The uncommitted ``_counts`` read is what makes the lock claim honest: it is
        taken on connection A, before B probes, and proves the endpoint had already
        reached its WRITES — so the row B cannot take is being held across the whole
        read-modify-write, not merely grabbed and dropped at the top.

        What it does NOT establish: which of two same-instant callers wins, or the
        blocked caller's eventual result — that outcome is the sequencing tests.
        """
        worker, dt, token = self._fixture(route)
        # The second connection can only see (and therefore lock) a committed row.
        frappe.db.commit()
        self.addCleanup(frappe.db.rollback)

        with self.primary_connection():
            self.assertEqual(
                run_endpoint(token),
                dt.name,
                "the endpoint must resolve to THIS test's trip (None = no boardable "
                "trip resolved at all, which is fixture bleed, not a broken lock)",
            )
            self.assertEqual(
                self._counts(dt.name, worker),
                (1, 1),
                "the endpoint must be past its log + boarding write, uncommitted, "
                "and therefore still inside its critical section",
            )

            with self.secondary_connection(), self.assertRaises(frappe.QueryTimeoutError):
                frappe.db.get_value(
                    "Dispatch Trip", dt.name, "name", for_update=True, wait=False
                )

            frappe.db.rollback()  # release the row; the fixture survives on its commit

    @timeout(15, "The confirm_boarding trip lock did not contend across connections")
    def test_confirm_boarding_holds_the_trip_lock_against_a_live_second_connection(self):
        """A LIVE confirm_boarding blocks a concurrent transaction on the trip row."""
        self._assert_live_endpoint_blocks_a_second_connection(
            _confirm_boarding_trip, "Worker Claim Race C"
        )

    @timeout(15, "The worker_claim_boarded trip lock did not contend across connections")
    def test_worker_claim_holds_the_trip_lock_against_a_live_second_connection(self):
        """A LIVE worker_claim_boarded blocks a concurrent transaction on the trip row.

        This test supplies ``worker_claim_boarded``'s only real contention coverage:
        the file's other cross-connection test for it runs the winner all the way to
        a COMMIT before the loser starts, so nothing is ever blocked there, and it
        would keep passing even with the endpoint's ``for_update`` read deleted. This
        one does not — it is the sibling of the confirm_boarding case above, over one
        body.
        """
        self._assert_live_endpoint_blocks_a_second_connection(
            _worker_claim_trip, "Worker Claim Race E"
        )

    @timeout(15, "Second connection did not serialize onto the committed confirm")
    def test_second_connection_confirm_merges_onto_the_committed_winner(self):
        """A confirm in its OWN transaction, after a committed winner, writes nothing new.

        Sequencing approximation, not interleaving: the winner has already committed
        when the loser starts, so nothing is ever blocked here. It proves the loser
        re-reads the committed boarding under the now-free lock and merges onto it.
        The blocking half is
        test_confirm_boarding_holds_the_trip_lock_against_a_live_second_connection.
        """
        worker, dt, token = self._fixture("Worker Claim Race D")
        # Flush the fixture — and any sibling's still-pending cleanup deletes — out
        # of the winner's transaction before it starts. The loser runs on a SEPARATE
        # connection and can only ever see committed rows.
        frappe.db.commit()
        self.addCleanup(frappe.db.rollback)

        with self.primary_connection():
            winner = masar.confirm_boarding(token=token)
            # Named before `created` is read: a wrong (or None) trip here means the
            # worker is on more than one live request, which is fixture bleed, not a
            # broken lock. Without it that shows up only as `created is False`.
            self.assertEqual(
                winner.get("dispatch_trip"),
                dt.name,
                "the winner must resolve to THIS test's trip (None = no boardable "
                "trip resolved at all)",
            )
            self.assertTrue(winner["created"], "the uncontended winner must record the boarding")
            frappe.db.commit()

        self.assertEqual(self._counts(dt.name, worker), (1, 1))

        with self.secondary_connection():
            loser = masar.confirm_boarding(token=token)
            frappe.db.commit()

        self.assertFalse(loser["created"], "the loser confirm must record no new boarding")
        self.assertEqual(
            frappe.db.count("Trip Start Log", {"dispatch_trip": dt.name, "docstatus": 0}),
            1,
            "the loser confirm must NOT open a second Trip Start Log",
        )
        self.assertEqual(
            frappe.db.count(
                "Trip Boarding Event",
                {"parent": loser["trip_start_log"], "parenttype": "Trip Start Log", "worker": worker},
            ),
            1,
            "the loser confirm must NOT append a second boarding event",
        )
