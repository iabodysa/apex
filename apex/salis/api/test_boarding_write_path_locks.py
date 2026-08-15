# Copyright (c) 2026, AFMCO and contributors
"""Every boarding write path takes the trip row lock BEFORE it get-or-creates the log.

A worker can be put aboard through three endpoints — ``boarding_flow.worker_claim_boarded``,
``masar.confirm_boarding`` and the manual fallback ``manual_boarding.board_worker``. Each
get-or-creates the trip's draft Trip Start Log, checks whether the worker is already
aboard, then appends a boarding event. That is a read-modify-write: two simultaneous
callers for one (trip, worker) both read "no open log / not aboard" and each writes,
leaving two Trip Start Logs and two Trip Boarding Events.

The driver scan path closed that window with a ``SELECT … FOR UPDATE`` on the Dispatch
Trip row before its get-or-create. This is the structural guard that ties the other three
to the same lock, so the window cannot be reopened by a later edit that moves the lock
below the create. ``scan_boarding_pass`` is deliberately absent — test_boarding_race.py
already owns it, and a second copy would be duplication.

Site-free: it reads the shipped source, so it runs anywhere the app imports. What it
cannot show is that the lock actually blocks a second connection; that is contention, and
it is proved for the scan path in test_boarding_race.py.
"""

from __future__ import annotations

import unittest

from apex.salis.api import boarding_flow, manual_boarding, masar
from apex.tests.source_tree import func_source

# (module, function, the get-or-create call the lock must precede)
LOCK_BEFORE_GET_OR_CREATE = [
    (boarding_flow, "worker_claim_boarded", "_get_or_create_trip_log("),
    (manual_boarding, "board_worker", "_get_or_create_log("),
    (masar, "confirm_boarding", "_get_or_create_trip_log("),
]


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


class TestBoardingWritePathsLockTheTrip(unittest.TestCase):
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

    def test_the_scan_reads_a_real_body_for_every_covered_path(self):
        """Guard-of-the-guard: an empty body would satisfy neither assertion above by
        accident, but a renamed function would make the whole loop vacuous."""
        for module, fname, _create in LOCK_BEFORE_GET_OR_CREATE:
            with self.subTest(function=fname):
                body = func_source(_read(module.__file__), module.__file__, fname)
                self.assertGreater(len(body.splitlines()), 5, f"{fname} body looks empty")
