# Copyright (c) 2026, AFMCO and contributors
"""Front Desk read-endpoint throttle.

``resolve_worker`` and its boarding sibling ``get_boarding_pass`` carry
``@rate_limit(key="frappe.request.remote_addr", limit=60, seconds=60)`` -- the
same per-IP cadence the Masar read endpoints use -- so a scanned-identifier probe
cannot be driven as an Iqama/token-enumeration oracle from one address.

Exception note: frappe's ``@rate_limit`` decorator raises
``frappe.RateLimitExceededError`` (a ``ValidationError`` with
``http_status_code == 429``) when the window is exceeded -- the in-process throttle.
``TooManyRequestsError`` is a *different*, conf-driven global limiter
(``rate_limiter.RateLimiter.reject``) that this decorator never raises; the
decorator's 429 is the faithful "too many requests" signal and is what these tests
assert (both the class and the 429 status).

``@rate_limit`` is a no-op without an HTTP request (``rate_limiter.py:134``); these
tests therefore stand up a minimal request context so the limit is actually
exercised. The decorator counts in Redis, so this is an integration test (live
bench), like the sibling concurrency tests.
"""

from __future__ import annotations

from contextlib import contextmanager

import frappe
from frappe.tests.utils import FrappeTestCase

from apex_habitat.habitat.api.front_desk import resolve_worker
from apex_habitat.salis.api.boarding import get_boarding_pass

# Matches the decorator on both endpoints; the 61st call in the window is rejected.
LIMIT = 60


class _FakeRequest:
    """The minimal surface frappe.rate_limiter.rate_limit reads off the request:
    a truthy object with an uppercase-able .method."""

    def __init__(self, method="GET"):
        self.method = method


def _h(n=8):
    return frappe.generate_hash(length=n).upper()


@contextmanager
def _request_from(ip: str, cmd: str):
    """Install a minimal request context (request, request_ip, form_dict.cmd) so
    the rate_limit decorator engages, then restore the prior local state. The
    cache key is rl:<cmd>:<ip>, so a unique cmd+ip per test isolates the window."""
    prev_request = getattr(frappe.local, "request", None)
    prev_ip = getattr(frappe.local, "request_ip", None)
    prev_form = getattr(frappe.local, "form_dict", None)
    frappe.local.request = _FakeRequest()
    frappe.local.request_ip = ip
    frappe.local.form_dict = frappe._dict({"cmd": cmd})
    try:
        yield
    finally:
        frappe.local.request = prev_request
        frappe.local.request_ip = prev_ip
        frappe.local.form_dict = prev_form if prev_form is not None else frappe._dict()


class TestFrontDeskRateLimit(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        # A unique IP per test so a leftover Redis counter from another run/test
        # never bleeds in; the key includes cmd + ip. (TEST-NET-3, RFC 5737.)
        self.ip = "203.0.113." + str(int(_h(4), 16) % 250 + 1)
        self.cmd = "test-rl-" + _h(6)

    def _clear_window(self, cmd, ip):
        frappe.cache.delete_value(frappe.cache.make_key(f"rl:{cmd}:{ip}"))

    def test_resolve_worker_throttles_the_61st_call_from_one_ip(self):
        cmd = self.cmd + "-rw"
        self.addCleanup(self._clear_window, cmd, self.ip)
        with _request_from(self.ip, cmd):
            # The first LIMIT calls pass (a benign unknown identifier -> found:False,
            # never throws on its own), proving the throttle does not bite the legit
            # cadence.
            for i in range(LIMIT):
                r = resolve_worker("NOPE-" + _h())
                self.assertFalse(r["found"], f"call {i + 1} should answer, not throttle")

            # The 61st call within the window is rejected.
            with self.assertRaises(frappe.RateLimitExceededError) as cm:
                resolve_worker("NOPE-" + _h())
            self.assertEqual(getattr(cm.exception, "http_status_code", None), 429)

    def test_get_boarding_pass_throttles_the_61st_call_from_one_ip(self):
        cmd = self.cmd + "-gbp"
        self.addCleanup(self._clear_window, cmd, self.ip)
        with _request_from(self.ip, cmd):
            # get_boarding_pass throws on an unknown trip (DoesNotExistError) BEFORE
            # any boarding logic, so each call still passes THROUGH the decorator
            # (the throttle wraps the call) without needing real trip fixtures. We
            # count those as the consumed window, then assert the 61st is throttled.
            for i in range(LIMIT):
                with self.assertRaises(frappe.DoesNotExistError):
                    get_boarding_pass("NO-SUCH-TRIP-" + _h(), "NO-EMP")

            with self.assertRaises(frappe.RateLimitExceededError) as cm:
                get_boarding_pass("NO-SUCH-TRIP-" + _h(), "NO-EMP")
            self.assertEqual(getattr(cm.exception, "http_status_code", None), 429)

    def test_distinct_ips_have_independent_windows(self):
        """The throttle is per-IP: a second address is unaffected by the first's
        spent window (non-vacuous -- proves the limit keys on remote_addr, not a
        global counter)."""
        cmd = self.cmd + "-iso"
        ip_a = "198.51.100.10"
        ip_b = "198.51.100.20"
        self.addCleanup(self._clear_window, cmd, ip_a)
        self.addCleanup(self._clear_window, cmd, ip_b)

        with _request_from(ip_a, cmd):
            for _ in range(LIMIT):
                resolve_worker("NOPE-" + _h())
            with self.assertRaises(frappe.RateLimitExceededError):
                resolve_worker("NOPE-" + _h())

        # A different IP still gets its full allowance.
        with _request_from(ip_b, cmd):
            r = resolve_worker("NOPE-" + _h())
            self.assertFalse(r["found"], "a different IP must not inherit IP A's spent window")

    def test_no_request_context_does_not_throttle(self):
        """Without an HTTP request the decorator is a no-op (rate_limiter.py:134),
        so the test suite / console callers are never throttled -- exactly why the
        functional boarding/resolve tests can loop freely."""
        # Far beyond LIMIT, no request context -> never raises.
        for _ in range(LIMIT + 5):
            self.assertFalse(resolve_worker("NOPE-" + _h())["found"])
