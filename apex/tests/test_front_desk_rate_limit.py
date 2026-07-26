# Copyright (c) 2026, AFMCO and contributors
"""Front Desk read-endpoint throttle.

``resolve_worker`` retains its 60-per-minute scan cadence while the driver-facing
``get_boarding_pass`` read uses the common 120-per-minute driver read limit. Both
are keyed per IP so a scanned-identifier probe cannot be driven without bound.
Driver boarding scans resolve a server-derived actor before charging the
60-per-minute actor ceiling. Only unresolved credentials may charge an IP
ceiling, so one authenticated driver behind a NAT cannot consume another
driver's scan capacity.

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

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.habitat.api.front_desk import resolve_worker
from apex.salis.api import boarding, driver_portal
from apex.salis.api.boarding import get_boarding_pass, scan_boarding_pass

# [#sxhul5]
LIMIT = 60
BOARDING_LIMIT = 120


class _FakeRequest:
    """Minimal v15 request surface used by rate limiting and token discovery."""

    def __init__(self, method="GET", cookies=None):
        self.method = method
        self.cookies = cookies or {}


def _h(n=12):
    return frappe.generate_hash(length=n).upper()


@contextmanager
def _request_from(ip: str, cmd: str, method="GET", cookies=None):
    """Install a minimal request context (request, request_ip, form_dict.cmd) so
    the rate_limit decorator engages, then restore the prior local state. The
    cache key is rl:<cmd>:<ip>, so a unique cmd+ip per test isolates the window."""
    absent = object()
    prev_request = getattr(frappe.local, "request", absent)
    prev_ip = getattr(frappe.local, "request_ip", absent)
    prev_form = getattr(frappe.local, "form_dict", absent)
    frappe.local.request = _FakeRequest(method, cookies)
    frappe.local.request_ip = ip
    frappe.local.form_dict = frappe._dict({"cmd": cmd})
    try:
        yield
    finally:
        for fieldname, previous in (
            ("request", prev_request),
            ("request_ip", prev_ip),
            ("form_dict", prev_form),
        ):
            if previous is absent:
                if hasattr(frappe.local, fieldname):
                    delattr(frappe.local, fieldname)
            else:
                setattr(frappe.local, fieldname, previous)


class TestFrontDeskRateLimit(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        # [#pqrpgg]
        self.ip = "203.0.113." + str(int(_h(12), 16) % 250 + 1)
        self.cmd = "test-rl-" + _h(12)

    def _drop_window(self, name):
        """Delete one rate-limit window by its RAW name, then prove it is gone.

        ``delete_value`` applies ``make_key`` itself (redis_wrapper.py:141-142), so
        handing it an already-made key prefixes the name a second time and clears
        nothing. These cleanups were green for months while deleting nothing, which
        is exactly why the absence is now asserted instead of assumed.
        """
        frappe.cache.delete_value(name)
        self.assertIsNone(
            frappe.cache.get(frappe.cache.make_key(name)),
            f"the rate-limit window {name} outlived its cleanup",
        )

    def _clear_window(self, cmd, ip):
        """The decorator's own window. ``key`` names a form_dict entry that a real
        request never carries, so the identity is ``ip`` joined to an empty string
        and the name ends in a bare colon (rate_limiter.py:145-155)."""
        self._drop_window(f"rl:{cmd}:{ip}:")

    def _clear_actor_window(self, cmd, actor):
        self._drop_window(f"rl:{cmd}:scan-actor:{actor}")

    def _clear_unresolved_scan_window(self, cmd, ip):
        self._drop_window(f"rl:{cmd}:scan-unresolved-ip:{ip}")

    def _driver_token(self):
        driver = frappe.get_doc(
            {
                "doctype": "Salis Driver",
                "full_name": "Rate Limit Driver " + _h(),
                "status": "Active",
            }
        ).insert(ignore_permissions=True)
        token = frappe.get_doc(
            {
                "doctype": "Masar Worker Token",
                "holder_type": "Driver",
                "driver": driver.name,
                "enabled": 1,
            }
        ).insert(ignore_permissions=True)
        frappe.db.set_value(
            "Masar Worker Token",
            token.name,
            {"party_type": None, "party": None, "employee": None},
            update_modified=False,
        )
        return driver.name, token._plaintext_token

    def _assert_guest_endpoint_throttles(self, endpoint, args, limit, method):
        cmd = self.cmd + "-" + endpoint.__name__
        self.addCleanup(self._clear_window, cmd, self.ip)
        frappe.set_user("Guest")
        with _request_from(self.ip, cmd, method):
            for _ in range(limit):
                with self.assertRaises(frappe.PermissionError):
                    endpoint(*args)
            with self.assertRaises(frappe.RateLimitExceededError) as cm:
                endpoint(*args)
        self.assertEqual(getattr(cm.exception, "http_status_code", None), 429)

    def test_guest_driver_read_throttles_without_weakening_authorization(self):
        self._assert_guest_endpoint_throttles(
            driver_portal.get_driver_profile,
            (),
            120,
            "GET",
        )

    def test_guest_driver_writer_throttles_without_weakening_authorization(self):
        self._assert_guest_endpoint_throttles(
            driver_portal.delete_push_subscription,
            ("https://push.example/subscription",),
            30,
            "POST",
        )

    def test_guest_driver_photo_writer_has_tight_throttle(self):
        self._assert_guest_endpoint_throttles(
            driver_portal.raise_support_ticket,
            ("Vehicle", "Medium", "Subject", "Description"),
            10,
            "POST",
        )

    def test_request_context_restores_previously_absent_request_state(self):
        sentinel = object()
        previous_request = getattr(frappe.local, "request", sentinel)
        previous_ip = getattr(frappe.local, "request_ip", sentinel)
        for fieldname in ("request", "request_ip"):
            if hasattr(frappe.local, fieldname):
                delattr(frappe.local, fieldname)
        try:
            with _request_from(self.ip, self.cmd):
                self.assertTrue(hasattr(frappe.local, "request"))
                self.assertTrue(hasattr(frappe.local, "request_ip"))
            self.assertFalse(hasattr(frappe.local, "request"))
            self.assertFalse(hasattr(frappe.local, "request_ip"))
        finally:
            for fieldname, previous in (
                ("request", previous_request),
                ("request_ip", previous_ip),
            ):
                if previous is sentinel:
                    if hasattr(frappe.local, fieldname):
                        delattr(frappe.local, fieldname)
                else:
                    setattr(frappe.local, fieldname, previous)

    def test_resolve_worker_throttles_the_61st_call_from_one_ip(self):
        cmd = self.cmd + "-rw"
        self.addCleanup(self._clear_window, cmd, self.ip)
        with _request_from(self.ip, cmd):
            # [#etrqqx]
            for i in range(LIMIT):
                r = resolve_worker("NOPE-" + _h())
                self.assertFalse(r["found"], f"call {i + 1} should answer, not throttle")

            # [#kp82cz]
            with self.assertRaises(frappe.RateLimitExceededError) as cm:
                resolve_worker("NOPE-" + _h())
            self.assertEqual(getattr(cm.exception, "http_status_code", None), 429)

    def test_get_boarding_pass_throttles_the_121st_call_from_one_ip(self):
        cmd = self.cmd + "-gbp"
        self.addCleanup(self._clear_window, cmd, self.ip)
        with _request_from(self.ip, cmd):
            # [#72k58u]
            for i in range(BOARDING_LIMIT):
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

        # [#x67r2c]
        with _request_from(ip_b, cmd):
            r = resolve_worker("NOPE-" + _h())
            self.assertFalse(r["found"], "a different IP must not inherit IP A's spent window")

    def test_scan_peak_quota_is_independent_for_two_drivers_behind_one_ip(self):
        driver_a, token_a = self._driver_token()
        driver_b, token_b = self._driver_token()
        cmd = self.cmd + "-scan-subject"
        self.addCleanup(self._clear_window, cmd, self.ip)
        self.addCleanup(self._clear_actor_window, cmd, driver_a)
        self.addCleanup(self._clear_actor_window, cmd, driver_b)
        previous_user = frappe.session.user
        frappe.set_user("Guest")
        try:
            with _request_from(
                self.ip,
                cmd,
                "POST",
                {"masar_dt": token_a},
            ):
                for _ in range(LIMIT):
                    self.assertEqual(
                        scan_boarding_pass("invalid-pass")["result"],
                        "Invalid Token",
                    )
                for _ in range(LIMIT, 301):
                    with self.assertRaises(frappe.RateLimitExceededError) as cm:
                        scan_boarding_pass("invalid-pass")
                    self.assertEqual(
                        getattr(cm.exception, "http_status_code", None), 429
                    )

            with _request_from(
                self.ip,
                cmd,
                "POST",
                {"masar_dt": token_b},
            ):
                try:
                    result = scan_boarding_pass("invalid-pass")
                except frappe.RateLimitExceededError:
                    result = None
                self.assertEqual(result and result["result"], "Invalid Token")
        finally:
            frappe.set_user(previous_user)
        self.assertEqual(frappe.session.user, previous_user)

    def test_scan_rejected_credentials_are_bounded_by_unresolved_ip(self):
        cmd = self.cmd + "-scan-unresolved"
        self.addCleanup(self._clear_unresolved_scan_window, cmd, self.ip)
        previous_user = frappe.session.user
        frappe.set_user("Guest")
        try:
            with _request_from(self.ip, cmd, "POST"):
                for _ in range(LIMIT):
                    with self.assertRaises(frappe.PermissionError):
                        scan_boarding_pass("invalid-pass")
                with self.assertRaises(frappe.RateLimitExceededError) as cm:
                    scan_boarding_pass("invalid-pass")
                self.assertEqual(getattr(cm.exception, "http_status_code", None), 429)
        finally:
            frappe.set_user(previous_user)

    def test_scan_bucket_initialization_is_atomic_and_expiry_is_not_refreshed(self):
        script = getattr(boarding, "SCAN_RATE_LIMIT_SCRIPT", None)
        self.assertIsInstance(script, str)

        cache = frappe.cache
        cache_key = cache.make_key(f"rl:{self.cmd}:scan-atomic:test-actor")
        cache.delete(cache_key)
        self.addCleanup(cache.delete, cache_key)

        workers = 32
        with ThreadPoolExecutor(max_workers=8) as executor:
            values = list(
                executor.map(
                    lambda _index: cache.eval(
                        script,
                        1,
                        cache_key,
                        boarding.SCAN_RATE_WINDOW_SECONDS,
                    ),
                    range(workers),
                )
            )

        self.assertEqual(sorted(int(value) for value in values), list(range(1, workers + 1)))
        self.assertGreater(cache.ttl(cache_key), 0)
        self.assertLessEqual(cache.ttl(cache_key), boarding.SCAN_RATE_WINDOW_SECONDS)

        cache.expire(cache_key, 1)
        value = cache.eval(
            script,
            1,
            cache_key,
            boarding.SCAN_RATE_WINDOW_SECONDS,
        )
        self.assertEqual(int(value), workers + 1)
        self.assertLessEqual(cache.ttl(cache_key), 1)

    def test_no_request_context_does_not_throttle(self):
        """Without an HTTP request the decorator is a no-op (rate_limiter.py:134),
        so the test suite / console callers are never throttled -- exactly why the
        functional boarding/resolve tests can loop freely."""
        # [#mohszr]
        for _ in range(LIMIT + 5):
            self.assertFalse(resolve_worker("NOPE-" + _h())["found"])

    def test_unresolved_scan_limiter_is_a_noop_without_request_context(self):
        absent = object()
        previous_request = getattr(frappe.local, "request", absent)
        previous_ip = getattr(frappe.local, "request_ip", absent)
        for fieldname in ("request", "request_ip"):
            if hasattr(frappe.local, fieldname):
                delattr(frappe.local, fieldname)
        try:
            boarding._enforce_scan_unresolved_ip_rate_limit()
        finally:
            for fieldname, previous in (
                ("request", previous_request),
                ("request_ip", previous_ip),
            ):
                if previous is absent:
                    if hasattr(frappe.local, fieldname):
                        delattr(frappe.local, fieldname)
                else:
                    setattr(frappe.local, fieldname, previous)
