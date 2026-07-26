# Copyright (c) 2026, AFMCO and contributors
"""The shared atomic fixed-window counter (A-219), proved against the shape it replaced.

An "atomic" counter nobody refuted is a claim, so atomicity is proved in two parts that
each cover the other's blind spot. The REFUTATION drives one late arrival at both shapes
and shows only the framework's read-then-write losing a full window; its interleaving is
forced rather than raced, so it can never flake — but a ``charge_window`` that regressed
to read-then-write would still pass it, because a caller whose read is fresh behaves
identically. The COMMAND COUNT closes that: the atomic shape issues one EVAL and never a
GET, so there is no interval between a read and a write for a second connection to
occupy at all.

Drives the REAL cache against constructed key names, so it needs no fixtures and writes
nothing to the database.
"""

import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest import mock

import frappe

from apex.apex_core.utils.rate_window import INCR_AND_EXPIRE_SCRIPT, charge_window

LIMIT = 10
WINDOW = 60


def _read_then_write(name, window_seconds, observed_empty=None):
    """The shape ``charge_window`` replaced: GET, then SETEX when the read said empty,
    then INCRBY (rate_limiter.py:134-166).

    Reproduced here ONLY so the fix can be refuted against it. ``observed_empty`` pins
    what this caller's GET returned, because that read is the whole defect: in a real
    flood it happened earlier, and the SETEX it authorises lands late.
    """
    key = frappe.cache.make_key(name)
    if observed_empty is None:
        observed_empty = not frappe.cache.get(key)
    if observed_empty:
        frappe.cache.setex(key, window_seconds, 0)
    return int(frappe.cache.incrby(key, 1))


class TestChargeWindow(unittest.TestCase):
    def _window(self):
        """One private window name per call, with a cleanup PROVED to land.

        The name stays RAW: ``delete_value`` re-applies ``make_key``
        (redis_wrapper.py:141-142), so handing it an already-made key prefixes the
        name twice and clears nothing.
        """
        name = "apex-rate-window-test:" + frappe.generate_hash(length=12)
        frappe.cache.delete_value(name)
        self.addCleanup(self._assert_cleared, name)
        self.addCleanup(frappe.cache.delete_value, name)
        return name

    def _assert_cleared(self, name):
        self.assertIsNone(
            frappe.cache.get(frappe.cache.make_key(name)),
            f"the window {name} outlived its cleanup",
        )

    def _count(self, name):
        return int(frappe.cache.get(frappe.cache.make_key(name)) or 0)

    def test_the_first_charge_opens_the_window_at_one_and_gives_it_a_ttl(self):
        name = self._window()
        self.assertEqual(charge_window(name, WINDOW, LIMIT), 1)
        self.assertEqual(self._count(name), 1)
        ttl = frappe.cache.ttl(frappe.cache.make_key(name))
        self.assertGreater(ttl, 0, "a window with no TTL never reopens")
        self.assertLessEqual(ttl, WINDOW)

    def test_the_hit_past_the_limit_is_refused_with_429_and_is_still_counted(self):
        name = self._window()
        for expected in range(1, LIMIT + 1):
            self.assertEqual(charge_window(name, WINDOW, LIMIT), expected)
        with self.assertRaises(frappe.RateLimitExceededError) as raised:
            charge_window(name, WINDOW, LIMIT)
        self.assertEqual(getattr(raised.exception, "http_status_code", None), 429)
        self.assertEqual(
            self._count(name),
            LIMIT + 1,
            "a refused hit must still be charged, or a flood pays nothing for being refused",
        )

    def test_a_later_hit_never_refreshes_the_window(self):
        """The TTL is set once, when the window opens. Refreshing it on every hit
        would let a steady stream hold one window open for as long as it keeps
        knocking, and the ceiling would never reset for the honest caller behind it."""
        name = self._window()
        charge_window(name, WINDOW, LIMIT)
        frappe.cache.expire(frappe.cache.make_key(name), 5)
        self.assertEqual(charge_window(name, WINDOW, LIMIT), 2)
        self.assertLessEqual(frappe.cache.ttl(frappe.cache.make_key(name)), 5)

    def test_the_charge_never_reads_the_counter_before_writing_it(self):
        """The half of the atomicity proof a regression cannot survive.

        The refutation below measures what a stale read costs, but it cannot catch a
        ``charge_window`` rewritten as read-then-write: a caller whose read is fresh
        behaves the same either way. What genuinely separates the two shapes is that
        this one never reads — one EVAL, no GET, no SETEX, no INCRBY — so no second
        connection has an interval to slip into.
        """
        name = self._window()
        cache = frappe.cache
        with mock.patch.object(cache, "eval", wraps=cache.eval) as script, (
            mock.patch.object(cache, "get", wraps=cache.get)
        ) as read, mock.patch.object(
            cache, "setex", wraps=cache.setex
        ) as reset, mock.patch.object(
            cache, "incrby", wraps=cache.incrby
        ) as bump:
            self.assertEqual(charge_window(name, WINDOW, LIMIT), 1)

        self.assertEqual(script.call_count, 1, "the whole charge must be ONE round trip")
        for spy, command in ((read, "GET"), (reset, "SETEX"), (bump, "INCRBY")):
            self.assertEqual(
                spy.call_count,
                0,
                f"charge_window issued a {command}, so read-then-write is back and "
                "with it the window a parallel flood can reset to zero",
            )

    def test_a_stale_first_request_cannot_reset_a_shared_window(self):
        """The refutation, with the interleaving forced instead of raced.

        A concurrent first request reads the key while the window is still empty;
        what it does next lands only after a burst has already filled that window.
        Under read-then-write its SETEX writes the counter back to zero and every
        count in the burst is erased, so the flood it was meant to expose becomes
        invisible. ``charge_window`` never reads before it writes, so the same late
        arrival can only add to the count.
        """
        burst = LIMIT + 2
        stale = self._window()
        shared = self._window()
        self.assertEqual(self._count(stale), 0)
        self.assertEqual(self._count(shared), 0)

        for index in range(burst):
            self.assertEqual(_read_then_write(stale, WINDOW), index + 1)
            if index < LIMIT:
                self.assertEqual(charge_window(shared, WINDOW, LIMIT), index + 1)
            else:
                with self.assertRaises(frappe.RateLimitExceededError):
                    charge_window(shared, WINDOW, LIMIT)
        self.assertEqual(self._count(stale), burst)
        self.assertEqual(self._count(shared), burst)

        self.assertEqual(
            _read_then_write(stale, WINDOW, observed_empty=True),
            1,
            "read-then-write must be shown losing the window, or this proves nothing",
        )
        self.assertEqual(self._count(stale), 1)
        with self.assertRaises(frappe.RateLimitExceededError):
            charge_window(shared, WINDOW, LIMIT)
        self.assertEqual(self._count(shared), burst + 1)

    def test_concurrent_callers_each_receive_a_distinct_count(self):
        """No two callers may be handed the same count, however they interleave.

        Asserts only what INCR always guarantees, so it cannot flake; the measurement
        that read-then-write does NOT guarantee it is the deterministic test above.
        """
        name = self._window()
        workers = 16
        cache = frappe.cache
        key = cache.make_key(name)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            seen = list(
                pool.map(
                    lambda _index: int(
                        cache.eval(INCR_AND_EXPIRE_SCRIPT, 1, key, WINDOW)
                    ),
                    range(workers),
                )
            )
        self.assertEqual(sorted(seen), list(range(1, workers + 1)))
        self.assertEqual(self._count(name), workers)


if __name__ == "__main__":
    unittest.main()
