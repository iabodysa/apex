# Copyright (c) 2026, afmcoltd
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

The one exception is ``TestUnresolvedScanAddressGuard`` at the foot of the file: it
spies the counter instead of spending it, so it needs neither a site nor Redis.

Size note: 330 test lines against 37 in the subject (8.9x), for 14 distinct behaviours. The ratio is arithmetic on a small subject, not overtesting — each test names a different one.
"""

from __future__ import annotations

import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from unittest import mock

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.apex_core.utils import rate_window
from apex.apex_core.utils.rate_limit_identity import canonical_command
from apex.salis.api import boarding, driver_portal

# Modules, never the metered functions themselves. A module-level ``from front_desk
# import resolve_worker`` publishes apex.apex_core.utils.test_front_desk_rate_limit.
# resolve_worker, which frappe resolves like any other dotted path
# (handler.py:294-303 -> __init__.py:1748-1750) while the window is named after the
# caller's spelling (rate_limiter.py:155) -- so the second name buys a second full
# window. This file ships in the package, so its names are as reachable as any.
from apex.habitat.api import front_desk

test_dependencies = ["Salis Driver"]

_ABSENT = object()

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
        """A cmd-named window, in BOTH identity shapes. Body-charged endpoints only.

        Un-keyed, which every endpoint this file drives now is (``resolve_worker``
        included, since that change): the identity is the bare address, so the name is
        ``rl:<cmd>:<ip>`` (rate_limiter.py:150,155). The ``@rate_limit`` endpoints no
        longer take their name from ``cmd`` at all and belong to
        ``_clear_metered_window``; what is left here charges in its own body.

        Keyed, which none is any longer: the identity was the address joined to a
        form_dict lookup, and a real request carries no field by that name, so the
        lookup yielded "" and the name ended in a bare colon (rate_limiter.py:143,
        147-148). The retired shape is still swept because a cleanup that clears a
        window by a HARDCODED name is silently vacuous the day the name changes:
        ``_drop_window`` deletes a name that was never created and then asserts it is
        absent, which stays GREEN while the window that WAS spent leaks into the next
        test. Dropping this line is only safe once nothing can produce the shape.
        """
        self._drop_window(f"rl:{cmd}:{ip}")
        self._drop_window(f"rl:{cmd}:{ip}:")

    def _clear_metered_window(self, endpoint, ip):
        """The window a ``@rate_limit`` endpoint really charges.

        Not ``rl:<this test's synthetic cmd>:<ip>``. Apex names those windows after the
        HANDLER (apex_core/utils/rate_limit_identity.py), precisely so two dotted paths
        to one function cannot buy two ceilings -- which also means the per-test ``cmd``
        no longer partitions them, and a cleanup written against it would delete a name
        that was never created while the spent window lived on for its full 60s. The
        endpoints charging in their own BODY (salis/api/boarding.py:164) still read
        ``cmd``, so those keep ``_clear_window``.
        """
        self._drop_window(f"rl:{canonical_command(endpoint)}:{ip}")

    def _clear_actor_window(self, cmd, actor):
        self._drop_window(f"rl:{cmd}:scan-actor:{actor}")

    def _clear_unresolved_scan_window(self, cmd, ip):
        self._drop_window(f"rl:{cmd}:scan-unresolved-ip:{ip}")

    def _driver_token(self, fixture):
        """A shipped Salis Driver and a live barcode for it.

        The subject is the CREDENTIAL, not the person, so two shipped Salis Drivers stand
        ready for any case that needs two distinct scan subjects to prove a quota is keyed
        per subject. ``driver`` is unique on the token, and FrappeTestCase rolls back per
        class, so the row is dropped when the case ends.
        """
        driver = frappe.db.get_value("Salis Driver", {"full_name": fixture})
        token = frappe.get_doc(
            {
                "doctype": "Masar Worker Token",
                "holder_type": "Driver",
                "driver": driver,
                "enabled": 1,
            }
        ).insert(ignore_permissions=True)
        self.addCleanup(
            frappe.delete_doc,
            "Masar Worker Token",
            token.name,
            force=True,
            ignore_permissions=True,
        )
        frappe.db.set_value(
            "Masar Worker Token",
            token.name,
            {"party_type": None, "party": None, "employee": None},
            update_modified=False,
        )
        return driver, token._plaintext_token

    def _assert_guest_endpoint_throttles(self, endpoint, args, limit, method):
        cmd = self.cmd + "-" + endpoint.__name__
        self.addCleanup(self._clear_metered_window, endpoint, self.ip)
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

    # The two writer cases below named ``delete_push_subscription`` and
    # ``raise_support_ticket``. Neither exists: the portal cutover retired
    # driver_portal/notifications.py and support.py outright, and
    # apex/www/test_portal_shell_contract.py asserts they stay gone. What the cases prove
    # is a PROPERTY of the guest writer tier, not those two names, so they are re-pointed
    # at the live writers that carry the same two throttle steps.

    def test_guest_driver_writer_throttles_without_weakening_authorization(self):
        self._assert_guest_endpoint_throttles(
            driver_portal.complete_my_trip,
            ("DT-DOES-NOT-EXIST",),
            30,
            "POST",
        )

    def test_guest_driver_photo_writer_has_tight_throttle(self):
        self._assert_guest_endpoint_throttles(
            driver_portal.start_my_trip,
            ("DT-DOES-NOT-EXIST",),
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
        self.addCleanup(self._clear_metered_window, front_desk.resolve_worker, self.ip)
        with _request_from(self.ip, cmd):
            for i in range(LIMIT):
                r = front_desk.resolve_worker("NOPE-" + _h())
                self.assertFalse(r["found"], f"call {i + 1} should answer, not throttle")

            with self.assertRaises(frappe.RateLimitExceededError) as cm:
                front_desk.resolve_worker("NOPE-" + _h())
            self.assertEqual(getattr(cm.exception, "http_status_code", None), 429)

    def test_get_boarding_pass_throttles_the_121st_call_from_one_ip(self):
        cmd = self.cmd + "-gbp"
        self.addCleanup(self._clear_window, cmd, self.ip)
        with _request_from(self.ip, cmd):
            for i in range(BOARDING_LIMIT):
                with self.assertRaises(frappe.DoesNotExistError):
                    boarding.get_boarding_pass("NO-SUCH-TRIP-" + _h(), "NO-EMP")

            with self.assertRaises(frappe.RateLimitExceededError) as cm:
                boarding.get_boarding_pass("NO-SUCH-TRIP-" + _h(), "NO-EMP")
            self.assertEqual(getattr(cm.exception, "http_status_code", None), 429)

    def test_distinct_ips_have_independent_windows(self):
        """The throttle is per-IP: a second address is unaffected by the first's
        spent window (non-vacuous -- proves the limit keys on remote_addr, not a
        global counter)."""
        cmd = self.cmd + "-iso"
        ip_a = "198.51.100.10"
        ip_b = "198.51.100.20"
        self.addCleanup(self._clear_metered_window, front_desk.resolve_worker, ip_a)
        self.addCleanup(self._clear_metered_window, front_desk.resolve_worker, ip_b)

        with _request_from(ip_a, cmd):
            for _ in range(LIMIT):
                front_desk.resolve_worker("NOPE-" + _h())
            with self.assertRaises(frappe.RateLimitExceededError):
                front_desk.resolve_worker("NOPE-" + _h())

        with _request_from(ip_b, cmd):
            r = front_desk.resolve_worker("NOPE-" + _h())
            self.assertFalse(r["found"], "a different IP must not inherit IP A's spent window")

    def test_scan_peak_quota_is_independent_for_two_drivers_behind_one_ip(self):
        driver_a, token_a = self._driver_token("_Test Driver")
        driver_b, token_b = self._driver_token("_Test Driver Two")
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
                        boarding.scan_boarding_pass("invalid-pass")["result"],
                        "Invalid Token",
                    )
                for _ in range(LIMIT, 301):
                    with self.assertRaises(frappe.RateLimitExceededError) as cm:
                        boarding.scan_boarding_pass("invalid-pass")
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
                    result = boarding.scan_boarding_pass("invalid-pass")
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
                        boarding.scan_boarding_pass("invalid-pass")
                with self.assertRaises(frappe.RateLimitExceededError) as cm:
                    boarding.scan_boarding_pass("invalid-pass")
                self.assertEqual(getattr(cm.exception, "http_status_code", None), 429)
        finally:
            frappe.set_user(previous_user)

    def test_scan_bucket_initialization_is_atomic_and_expiry_is_not_refreshed(self):
        # The counter is shared, so the script is read from the module that OWNS it
        # rather than through a re-export kept alive only for this line.
        script = rate_window.INCR_AND_EXPIRE_SCRIPT
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
        for _ in range(LIMIT + 5):
            self.assertFalse(front_desk.resolve_worker("NOPE-" + _h())["found"])

    def test_unresolved_scan_limiter_is_a_noop_without_request_context(self):
        """No request at all, so a console or job caller is never charged.

        This deletes the REQUEST, which is the limiter's FIRST guard (boarding.py:165),
        so the address read below it never runs here -- what this covers is the outer
        contract only. ``TestUnresolvedScanAddressGuard`` is what reaches the second
        guard, the one that decides what a request with NO address costs.
        """
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


class TestUnresolvedScanAddressGuard(unittest.TestCase):
    """A request that carries NO address, which the class above cannot reach.

    ``test_unresolved_scan_limiter_is_a_noop_without_request_context`` deletes the
    request too, so the guard on ``frappe.local.request`` short-circuits and the
    address is never read -- it passed against the bare read it was meant to cover.
    Here the request is PRESENT and only the address is missing, in both shapes it
    occurs in: unset (``AttributeError`` from the bare read) and None (``frappe.init``
    sets it, ``frappe.app`` fills it, so None is what every non-HTTP caller carries).
    A None address charged a bucket literally named ``...:None`` -- one window shared
    by every addressless caller in the app, which is the opposite of a per-address
    ceiling and would 429 an innocent third party.

    ``charge_window`` is spied rather than spent, so what is asserted is the DECISION
    to charge. That needs no site and no Redis, which is the whole point: a throttle
    whose guards can only be exercised against a live bench is a throttle whose guards
    do not get tested.
    """

    def setUp(self):
        self._saved = {
            name: getattr(frappe.local, name, _ABSENT)
            for name in ("request", "request_ip", "form_dict")
        }
        self.addCleanup(self._restore)
        self.charged = []
        spy = mock.patch.object(
            boarding,
            "charge_window",
            side_effect=lambda name, window, limit: self.charged.append(name) or 1,
        )
        spy.start()
        self.addCleanup(spy.stop)
        frappe.local.form_dict = frappe._dict({"cmd": "a226-" + _h()})

    def _restore(self):
        for name, previous in self._saved.items():
            if previous is _ABSENT:
                if hasattr(frappe.local, name):
                    delattr(frappe.local, name)
            else:
                setattr(frappe.local, name, previous)

    def test_a_request_with_no_address_declines_instead_of_charging(self):
        for label, install_none in (("unset", False), ("None", True)):
            with self.subTest(request_ip=label):
                self.charged.clear()
                if hasattr(frappe.local, "request_ip"):
                    delattr(frappe.local, "request_ip")
                if install_none:
                    frappe.local.request_ip = None
                frappe.local.request = _FakeRequest("POST")

                self.assertIsNone(boarding._enforce_scan_unresolved_ip_rate_limit())
                self.assertEqual(
                    self.charged,
                    [],
                    "an addressless caller was charged, so every one of them shares "
                    "a single window and any of them can 429 the rest",
                )

    def test_the_guard_still_charges_a_request_that_has_an_address(self):
        """Non-vacuous: the guard must decline an absent address, not every call.

        Without this, replacing the whole body with ``return`` would pass the test
        above and quietly retire the only ceiling on rejected scan credentials. The
        address stays inside this file's own 203.0.113.0/24 slice (RFC 5737) even
        though a spied charge never reaches a shared window.
        """
        frappe.local.request = _FakeRequest("POST")
        frappe.local.request_ip = "203.0.113." + str(int(_h(12), 16) % 250 + 1)

        boarding._enforce_scan_unresolved_ip_rate_limit()

        self.assertEqual(len(self.charged), 1)
        self.assertIn(":scan-unresolved-ip:", self.charged[0])
        self.assertTrue(self.charged[0].endswith(frappe.local.request_ip))
