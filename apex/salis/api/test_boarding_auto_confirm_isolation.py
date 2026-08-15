# Copyright (c) 2026, AFMCO and contributors
"""One bad trip must not discard the whole auto-confirm run.

``auto_confirm_claimed_boardings`` is a scheduled tick (hooks.py:310) that walks
every Dispatch Trip carrying a timed-out worker claim and saves each one. Frappe
runs a scheduled method inside ONE transaction and, when the method raises,
rolls that whole transaction back before marking the job Failed
(scheduled_job_type.py:151-156). The loop commits only after it finishes
(boarding_flow.py:348), so an exception escaping any iteration discarded every
trip already confirmed in that run — and, because the tick re-reads the same
rows next time, the same bad trip stalled every later run too.

This pins the isolation contract that fixes it: each trip is written inside its
own savepoint, so a failing one is rolled back to that savepoint and logged while
the remaining trips still confirm and commit. Covers both write points — the
``get_doc`` read of the trip and the ``save`` of the flipped rows.

Site-free: only the module's own ``frappe`` is exercised, so it is swapped for a
stub. The timeout arithmetic belongs to ``_apply_auto_confirm`` and is pinned by
its own suites; this file pins the loop, so the flip is stubbed constant.
"""

import unittest
from unittest.mock import patch

from apex.salis.api import boarding_flow

_SAVEPOINT = "salis_boarding_auto_confirm_row"


class _Trip:
    def __init__(self, name, fail_on_save):
        self.name = name
        self._fail_on_save = fail_on_save

    def save(self, **_kwargs):
        if self._fail_on_save:
            raise ValueError(f"save refused for {self.name}")


class _StubDB:
    def __init__(self):
        self.savepoints = []
        self.rollbacks = []
        self.commits = 0

    def savepoint(self, save_point):
        self.savepoints.append(save_point)

    def rollback(self, save_point=None):
        self.rollbacks.append(save_point)

    def commit(self):
        self.commits += 1


class _StubFrappe:
    def __init__(self, trips, fail_get, fail_save):
        self.db = _StubDB()
        self._trips = trips
        self._fail_get = fail_get
        self._fail_save = fail_save
        self.saved = []
        self.errors = []
        self.locked = []

    def get_all(self, *_args, **_kwargs):
        return list(self._trips)

    def get_doc(self, _doctype, name, **kwargs):
        # The tick loads through boarding_flow._locked_trip, which passes for_update so
        # both the trip row and its boarding rows are read under lock. Recorded rather
        # than swallowed, so a load that quietly stopped locking shows up here.
        if kwargs.get("for_update"):
            self.locked.append(name)
        if name in self._fail_get:
            raise ValueError(f"trip {name} could not be loaded")
        return _Trip(name, name in self._fail_save)

    def log_error(self, **kwargs):
        self.errors.append(kwargs.get("title", ""))

    def get_traceback(self):
        return "traceback"

    def publish_realtime(self, *_args, **_kwargs):
        pass


def _run(trips, fail_get=(), fail_save=()):
    stub = _StubFrappe(trips, set(fail_get), set(fail_save))
    saved = []

    def _flip(trip):
        saved.append(trip.name)
        return 1

    with patch.object(boarding_flow, "frappe", stub), patch.object(
        boarding_flow, "_apply_auto_confirm", _flip
    ):
        confirmed = boarding_flow.auto_confirm_claimed_boardings()
    # a trip that raised inside save() still reached _apply_auto_confirm
    return confirmed, stub, saved


class TestOneBadTripDoesNotDiscardTheRun(unittest.TestCase):
    def test_a_trip_that_cannot_be_loaded_does_not_abort_the_others(self):
        confirmed, stub, _ = _run(
            ["T-OK-1", "T-BAD-GET", "T-OK-2"], fail_get=["T-BAD-GET"]
        )
        self.assertEqual(confirmed, 2, "both healthy trips must still confirm")
        self.assertEqual(stub.errors and len(stub.errors), 1, "the bad trip must be logged")

    def test_a_trip_that_cannot_be_saved_does_not_abort_the_others(self):
        confirmed, stub, _ = _run(
            ["T-OK-1", "T-BAD-SAVE", "T-OK-2"], fail_save=["T-BAD-SAVE"]
        )
        self.assertEqual(confirmed, 2, "a failed save must not cost the healthy trips")
        self.assertEqual(len(stub.errors), 1)

    def test_the_failure_is_rolled_back_to_its_own_savepoint(self):
        """A BARE rollback here would discard every trip already confirmed in this
        run — the exact whole-run loss this contract exists to stop."""
        _, stub, _ = _run(["T-OK-1", "T-BAD-SAVE"], fail_save=["T-BAD-SAVE"])
        self.assertEqual(
            stub.db.rollbacks,
            [_SAVEPOINT],
            "the failing trip must roll back to its row savepoint, never bare",
        )
        self.assertNotIn(
            None, stub.db.rollbacks, "a bare rollback would discard the whole run"
        )

    def test_every_trip_is_written_inside_a_savepoint(self):
        _, stub, _ = _run(["T-OK-1", "T-OK-2", "T-OK-3"])
        self.assertEqual(stub.db.savepoints, [_SAVEPOINT] * 3)

    def test_the_healthy_trips_are_still_committed(self):
        confirmed, stub, _ = _run(["T-OK-1", "T-BAD-SAVE"], fail_save=["T-BAD-SAVE"])
        self.assertEqual(confirmed, 1)
        self.assertEqual(stub.db.commits, 1, "the surviving work must still be committed")

    def test_every_trip_is_loaded_under_the_row_lock(self):
        """The tick writes boarding_state like every other door, so it serialises like
        every other door — a plain load here would race a worker's self-confirm."""
        _, stub, _ = _run(["T-OK-1", "T-OK-2"])
        # A set, because the loop walks set(trips) and its order rides PYTHONHASHSEED.
        self.assertEqual(set(stub.locked), {"T-OK-1", "T-OK-2"})

    def test_a_clean_run_is_unchanged(self):
        confirmed, stub, _ = _run(["T-OK-1", "T-OK-2"])
        self.assertEqual(confirmed, 2)
        self.assertEqual(stub.db.rollbacks, [])
        self.assertEqual(stub.db.commits, 1)

    def test_no_eligible_trip_commits_nothing(self):
        confirmed, stub, _ = _run([])
        self.assertEqual(confirmed, 0)
        self.assertEqual(stub.db.commits, 0, "an empty run must not commit")


if __name__ == "__main__":
    unittest.main()
