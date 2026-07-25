# Copyright (c) 2026, AFMCO and contributors
"""Boarding-scan race guard.

Two concurrent VALID scans of the same (trip, worker) must not both pass the
``_already_boarded`` check on a stale read and write two Trip Start Logs / two
boarding events. ``scan_boarding_pass`` takes a ``SELECT ... FOR UPDATE`` on the
Dispatch Trip row BEFORE get-or-create-log + the dup-check + append, so the second
scan serializes behind the first commit and resolves to ``Duplicate``.

This file proves three things, mirroring test_routed_payment_concurrency /
test_stock_source_locking:

  1. Functional half (sequential): two valid scans of one (trip, worker) yield
     exactly one Trip Start Log, one boarding event, and a second result of
     ``Duplicate`` -- the invariant the lock enforces under true concurrency.
  2. Concurrency half (real two-connection DB lock): while connection A holds the
     EXACT Dispatch Trip row lock the scan opens its critical section with,
     connection B's locking read with ``wait=False`` is rejected
     (``QueryTimeoutError``) -- literal cross-transaction contention, not a
     sequential re-call.
  3. Structural guard (AST, no site): the Dispatch Trip ``for_update`` lock
     precedes the ``_get_or_create_log`` call inside ``scan_boarding_pass`` (the
     race window is closed at the source).
"""

from __future__ import annotations


import frappe
from frappe.tests.utils import FrappeTestCase, timeout

from apex.salis.api import boarding as _boarding_mod
from apex.salis.api.boarding import (
    _issue_token,
    get_boarding_pass,
    scan_boarding_pass,
)
from apex.tests.source_tree import func_source

# Source path resolved from the module itself so this AST guard is independent of
# where the test file lives (it was moved out of apex/salis/api/ into apex/tests/).
_BOARDING_SRC = _boarding_mod.__file__


def _h(n=12):
    return frappe.generate_hash(length=n).upper()


class TestBoardingRace(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self._cleanup = []

        # [#f408rj]
        self.employee = frappe.get_doc({
            "doctype": "Employee",
            "first_name": "EMP-" + _h(12),
            "naming_series": "HR-EMP-",
        })
        self.employee.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        self._cleanup.append(("Employee", self.employee.name))

        self.request = frappe.get_doc({
            "doctype": "Transport Request",
            "request_date": "2026-06-20",
        })
        self.request.append("workers", {"employee": self.employee.name})
        self.request.flags.ignore_validate = True
        self.request.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        self._cleanup.append(("Transport Request", self.request.name))

        self.trip = frappe.get_doc({
            "doctype": "Dispatch Trip",
            "naming_series": "DT-.######",
            "transport_request": self.request.name,
            "trip_date": "2026-06-20",
            "status": "Planned",
        })
        self.trip.flags.ignore_validate = True
        self.trip.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        self._cleanup.append(("Dispatch Trip", self.trip.name))

    def tearDown(self):
        frappe.set_user("Administrator")
        # [#k7fjnk]
        for tsl in frappe.get_all(
            "Trip Start Log", filters={"dispatch_trip": self.trip.name}, pluck="name"
        ):
            frappe.db.set_value("Trip Start Log", tsl, "docstatus", 0, update_modified=False)
            frappe.delete_doc("Trip Start Log", tsl, force=True, ignore_permissions=True)
        for bsl in frappe.get_all(
            "Boarding Scan Log", filters={"dispatch_trip": self.trip.name}, pluck="name"
        ):
            frappe.delete_doc("Boarding Scan Log", bsl, force=True, ignore_permissions=True)
        for dt, name in reversed(self._cleanup):
            frappe.delete_doc(dt, name, force=True, ignore_permissions=True)

    def _token(self):
        """A genuine signed pass for (trip, worker) -- minted directly so the
        rate_limit decorator on get_boarding_pass is irrelevant to this test."""
        return _issue_token(self.trip.name, self.employee.name)

    # [#ifpp59]
    def test_two_valid_scans_produce_one_log_one_event_second_duplicate(self):
        token = self._token()

        first = scan_boarding_pass(token)
        self.assertEqual(first["result"], "Valid")

        second = scan_boarding_pass(token)
        self.assertEqual(second["result"], "Duplicate", "a repeat scan is a Duplicate")

        # [#1fjxhx]
        logs = frappe.get_all("Trip Start Log", filters={"dispatch_trip": self.trip.name}, pluck="name")
        self.assertEqual(len(logs), 1, "two scans must open exactly one Trip Start Log")
        self.assertEqual(first["trip_start_log"], second["trip_start_log"])

        # [#8arhwb]
        events = frappe.get_all(
            "Trip Boarding Event",
            filters={"parent": logs[0], "worker": self.employee.name},
            pluck="name",
        )
        self.assertEqual(len(events), 1, "two scans must append exactly one boarding event")

    def test_get_boarding_pass_round_trips_into_a_valid_scan(self):
        """The issued pass (the read endpoint) scans Valid once and Duplicate
        again -- proving the minted token in the race test is representative."""
        pas = get_boarding_pass(self.trip.name, self.employee.name)
        self.assertEqual(scan_boarding_pass(pas["pass_token"])["result"], "Valid")
        self.assertEqual(scan_boarding_pass(pas["pass_token"])["result"], "Duplicate")

    # [#aerrc8]
    def test_replayed_valid_pass_within_ttl_is_duplicate_no_second_effect(self):
        token = self._token()  # [#3rd84u]

        first = scan_boarding_pass(token)
        self.assertEqual(first["result"], "Valid")

        # [#kh127e]
        for _i in range(3):
            replay = scan_boarding_pass(token)
            self.assertEqual(
                replay["result"], "Duplicate",
                "a replayed pass within TTL must resolve to Duplicate, never re-board",
            )
            self.assertEqual(
                replay["trip_start_log"], first["trip_start_log"],
                "a replay must reuse the original log, never open a new one",
            )

        # [#l0d4di]
        logs = frappe.get_all(
            "Trip Start Log", filters={"dispatch_trip": self.trip.name}, pluck="name"
        )
        self.assertEqual(len(logs), 1, "replays must NOT open a second Trip Start Log")
        events = frappe.get_all(
            "Trip Boarding Event",
            filters={"parent": logs[0], "worker": self.employee.name},
            pluck="name",
        )
        self.assertEqual(len(events), 1, "replays must NOT append a second boarding event")

        # [#gznq8s]
        self.assertEqual(
            frappe.db.get_value("Trip Start Log", logs[0], "boarded_count"), 1,
            "boarded_count is derived from boarding events; replays must not inflate it",
        )

        # [#nssps6]
        self.assertEqual(
            frappe.db.count(
                "Boarding Scan Log",
                {"dispatch_trip": self.trip.name, "employee": self.employee.name, "result": "Valid"},
            ),
            1,
            "exactly one Valid scan-log row",
        )
        self.assertEqual(
            frappe.db.count(
                "Boarding Scan Log",
                {"dispatch_trip": self.trip.name, "employee": self.employee.name, "result": "Duplicate"},
            ),
            3,
            "each replay records a Duplicate audit row, no boarding side effect",
        )

    # [#8vs42o]
    @timeout(15, "The Dispatch Trip scan lock did not contend across connections")
    def test_concurrent_scan_lock_blocks_second_connection(self):
        """Two live transactions cannot both hold the Dispatch Trip row lock.

        Connection A takes the EXACT lock scan_boarding_pass opens its critical
        section with -- get_value(Dispatch Trip, for_update=True) -- and holds it
        uncommitted. Connection B, standing in for a concurrent scan, takes the
        same locking read with wait=False and is rejected (QueryTimeoutError):
        proof the InnoDB row lock serializes the two scans, so the second cannot
        reach _already_boarded (and double-board) while the first holds the row.
        """
        frappe.db.commit()  # [#sl75fw]
        self.addCleanup(frappe.db.rollback)

        with self.primary_connection():
            locked = frappe.db.get_value("Dispatch Trip", self.trip.name, "name", for_update=True)
            self.assertEqual(locked, self.trip.name)

            with self.secondary_connection(), self.assertRaises(frappe.QueryTimeoutError):
                frappe.db.get_value(
                    "Dispatch Trip", self.trip.name, "name", for_update=True, wait=False
                )

    @timeout(15, "Second connection did not serialize onto the committed boarding")
    def test_loser_connection_sees_duplicate_after_winner_commits(self):
        """A second scan in its OWN transaction merges to Duplicate, no second row.

        Connection A runs the full scan and commits -- the winner: one Trip Start
        Log, one event. Connection B then scans the same (trip, worker) in a
        separate transaction; it takes the now-free lock, re-reads the committed
        boarding under the lock and returns Duplicate -- no second log, no second
        event. The serialized loser's path across two real connections.
        """
        token = self._token()

        with self.primary_connection():
            first = scan_boarding_pass(token)
            frappe.db.commit()
        self.assertEqual(first["result"], "Valid")

        logs_after_winner = frappe.db.count("Trip Start Log", {"dispatch_trip": self.trip.name})
        events_after_winner = frappe.db.count(
            "Trip Boarding Event", {"parent": first["trip_start_log"], "worker": self.employee.name}
        )

        with self.secondary_connection():
            second = scan_boarding_pass(token)
            frappe.db.commit()

        self.assertEqual(second["result"], "Duplicate", "serialized loser must be a Duplicate")
        self.assertEqual(
            frappe.db.count("Trip Start Log", {"dispatch_trip": self.trip.name}),
            logs_after_winner,
            "loser scan must NOT open a second Trip Start Log",
        )
        self.assertEqual(
            frappe.db.count(
                "Trip Boarding Event",
                {"parent": first["trip_start_log"], "worker": self.employee.name},
            ),
            events_after_winner,
            "loser scan must NOT append a second boarding event",
        )

    # [#tizr1n]
    def test_scan_locks_trip_before_get_or_create_log(self):
        src = _read(_BOARDING_SRC)
        body = func_source(src, _BOARDING_SRC, "scan_boarding_pass")
        lock_pos = body.find('get_value("Dispatch Trip"')
        # [#1u42zt]
        lock_line = next(
            (ln for ln in body.splitlines() if 'get_value("Dispatch Trip"' in ln and "for_update=True" in ln),
            None,
        )
        self.assertIsNotNone(
            lock_line,
            "scan_boarding_pass must take a for_update lock on the Dispatch Trip row",
        )
        create_pos = body.find("_get_or_create_log(")
        self.assertGreater(lock_pos, -1, "Dispatch Trip lock read not found")
        self.assertGreater(create_pos, -1, "_get_or_create_log call not found")
        self.assertLess(
            lock_pos,
            create_pos,
            "the Dispatch Trip lock must precede _get_or_create_log (race window guard removed?)",
        )

    def test_get_or_create_log_uses_ignore_permissions(self):
        """Sanity: the helper still inserts the log audit-ok (the lock does not
        change the authorization model, only the ordering)."""
        self.assertIn("ignore_permissions=True", func_source(
            _read(_BOARDING_SRC), _BOARDING_SRC, "_get_or_create_log"))


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


