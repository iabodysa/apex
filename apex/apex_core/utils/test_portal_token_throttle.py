# Copyright (c) 2026, AFMCO and contributors
"""Portal bad-token throttle (A-110), proved in BOTH directions.

A rate limiter nobody proved fires is not hardening; one nobody proved lets real
users through is an outage. These drive the REAL throttle and the REAL cache against
a constructed request, so they need no served site and no fixtures: the only thing
stubbed is the token row lookup, which keeps the whole module DB-write-free.

The counterpart integration coverage in ``apex/tests/test_portal_token_security.py``
exercises the same guard against real ``Masar Worker Token`` rows.
"""

import unittest
from unittest import mock

import frappe

from apex.apex_core.utils import portal_token_security as token_security
from apex.www import driver as driver_page, masar as masar_page

LIMIT = token_security.BAD_TOKEN_ATTEMPTS_PER_MINUTE
BOGUS = "definitely-not-an-issued-portal-token"
VALID = "an-issued-portal-token"
DRIVER_SUBJECT = "A110-DRIVER"
WORKER_SUBJECT = "A110-EMPLOYEE"
SUBJECTS = {
    token_security.WORKER: WORKER_SUBJECT,
    token_security.DRIVER: DRIVER_SUBJECT,
}


class _Request:
    """The two attributes the resolver and the limiter read off a request."""

    def __init__(self, cookies=None):
        self.cookies = cookies or {}
        self.method = "GET"


def _valid_row(audience):
    """A row that satisfies validate_subject_binding for exactly this audience."""
    expires_on = frappe.utils.add_days(frappe.utils.now_datetime(), 30)
    if audience == token_security.WORKER:
        return {
            "holder_type": token_security.WORKER,
            "party_type": "Employee",
            "party": WORKER_SUBJECT,
            "employee": WORKER_SUBJECT,
            "driver": None,
            "expires_on": expires_on,
        }
    return {
        "holder_type": token_security.DRIVER,
        "party_type": None,
        "party": None,
        "employee": None,
        "driver": DRIVER_SUBJECT,
        "expires_on": expires_on,
    }


class TestPortalTokenThrottle(unittest.TestCase):
    """Both directions of the failed-token throttle, on a constructed request."""

    def setUp(self):
        self._saved = {
            name: getattr(frappe.local, name, None)
            for name in ("request", "request_ip", "form_dict")
        }
        self.addCleanup(self._restore)

    def _restore(self):
        for name, value in self._saved.items():
            setattr(frappe.local, name, value)

    def _arm(self, ip=None, cmd=None, cookies=None):
        """Stand up one request surface and return its throttle key NAME.

        The window is keyed on the ADDRESS ALONE, so a unique address per call is
        what buys a fresh window; ``cmd`` is set only to prove the key ignores it.
        The name handed to the cache is deliberately RAW: ``delete_value`` re-applies
        ``make_key`` (redis_wrapper.py:141-142), so an already-made key is prefixed a
        second time and clears nothing.
        """
        ip = ip or "2001:db8::" + frappe.generate_hash(length=12)
        frappe.local.request = _Request(cookies)
        frappe.local.request_ip = ip
        cmd = cmd if cmd is not None else "a110-" + frappe.generate_hash(length=12)
        frappe.local.form_dict = frappe._dict({"cmd": cmd} if cmd else {})
        name = token_security.BAD_TOKEN_WINDOW_KEY.format(ip)
        frappe.cache.delete_value(name)
        self.addCleanup(self._assert_window_cleared, name)
        self.addCleanup(frappe.cache.delete_value, name)
        return name

    def _assert_window_cleared(self, name):
        """Registered BEFORE the delete so LIFO runs it AFTER: the cleanup is proved
        to land, not merely to have been written (the A-209 dead-cleanup bug)."""
        self.assertIsNone(
            frappe.cache.get(frappe.cache.make_key(name)),
            f"the throttle window {name} outlived its cleanup",
        )

    def _counter(self, name):
        return int(frappe.cache.get(frappe.cache.make_key(name)) or 0)

    def _token_reads(self):
        """Stub ONLY the token and subject-status reads, so no row has to exist."""
        real = frappe.db.get_value

        def _side_effect(doctype, filters=None, fieldname=None, *args, **kwargs):
            if doctype == "Masar Worker Token":
                if filters.get("token") != token_security.hash_token(VALID):
                    return None
                return _valid_row(filters.get("holder_type"))
            if doctype in ("Employee", "Salis Driver") and filters in SUBJECTS.values():
                return "Active"
            return real(doctype, filters, fieldname, *args, **kwargs)

        return mock.patch.object(
            token_security.frappe.db, "get_value", side_effect=_side_effect
        )

    def test_a_flood_of_bad_tokens_is_cut_off_with_429(self):
        """The first N failures fail closed with the ordinary 403; the (N+1)th is
        refused by the limiter with RateLimitExceededError / HTTP 429."""
        name = self._arm()
        with self._token_reads():
            for attempt in range(LIMIT):
                with self.subTest(attempt=attempt), self.assertRaises(
                    frappe.PermissionError
                ):
                    token_security.resolve_portal_subject(
                        token_security.DRIVER, BOGUS, required=True
                    )
            with self.assertRaises(frappe.RateLimitExceededError) as raised:
                token_security.resolve_portal_subject(
                    token_security.DRIVER, BOGUS, required=True
                )

        self.assertEqual(getattr(raised.exception, "http_status_code", None), 429)
        self.assertEqual(self._counter(name), LIMIT + 1)

    def test_a_valid_link_is_never_charged_however_often_it_is_reloaded(self):
        """A resident who reloads, plus a service worker re-fetch, must never be
        throttled: only FAILED resolutions are charged, so the window stays empty."""
        name = self._arm()
        with self._token_reads():
            resolved = [
                token_security.resolve_portal_subject(
                    token_security.DRIVER, VALID, required=True
                )
                for _ in range(LIMIT * 3)
            ]

        self.assertEqual(set(resolved), {DRIVER_SUBJECT})
        self.assertEqual(self._counter(name), 0)

    def test_an_exhausted_window_still_admits_a_valid_link_from_the_same_address(self):
        """The accepted IP-keying failure mode, bounded: one abuser on a shared
        office NAT must not lock out a colleague whose link actually works."""
        name = self._arm()
        with self._token_reads():
            for _ in range(LIMIT + 1):
                with self.assertRaises(
                    (frappe.PermissionError, frappe.RateLimitExceededError)
                ):
                    token_security.resolve_portal_subject(
                        token_security.DRIVER, BOGUS, required=True
                    )
            self.assertGreater(self._counter(name), LIMIT)
            self.assertEqual(
                token_security.resolve_portal_subject(
                    token_security.DRIVER, VALID, required=True
                ),
                DRIVER_SUBJECT,
            )

        self.assertEqual(self._counter(name), LIMIT + 1)

    def test_every_bad_link_still_redirects_until_the_entry_window_is_spent(self):
        """A bad link must still redirect to the clean URL so the secret leaves the
        address bar; only past the ceiling does the entry answer 429 instead."""
        for page, field in ((masar_page, "w"), (driver_page, "d")):
            with self.subTest(entry=page.__name__):
                name = self._arm(cmd="")
                with self._token_reads(), mock.patch.object(
                    page, "get_csrf_token", return_value="csrf"
                ):
                    for attempt in range(LIMIT):
                        frappe.local.form_dict[field] = BOGUS
                        with self.subTest(attempt=attempt), self.assertRaises(
                            frappe.Redirect
                        ):
                            page.get_context(frappe._dict())
                    frappe.local.form_dict[field] = BOGUS
                    with self.assertRaises(frappe.RateLimitExceededError) as raised:
                        page.get_context(frappe._dict())

                self.assertEqual(
                    getattr(raised.exception, "http_status_code", None), 429
                )
                self.assertEqual(self._counter(name), LIMIT + 1)

    def test_a_page_load_and_a_reload_both_succeed_on_a_valid_link(self):
        """The outage check on the entry itself: the QR/personal link redirects, and
        the reload that follows renders off the cookie -- neither is charged."""
        for page, field, cookie in (
            (masar_page, "w", "masar_wt"),
            (driver_page, "d", "masar_dt"),
        ):
            with self.subTest(entry=page.__name__):
                name = self._arm(cmd="")
                with self._token_reads(), mock.patch.object(
                    page, "get_csrf_token", return_value="csrf"
                ):
                    frappe.local.form_dict[field] = VALID
                    with self.assertRaises(frappe.Redirect):
                        page.get_context(frappe._dict())

                    frappe.local.form_dict.pop(field, None)
                    frappe.local.request = _Request({cookie: VALID})
                    self.assertIsNotNone(page.get_context(frappe._dict()))

                self.assertEqual(self._counter(name), 0)

    def test_both_www_entries_spend_one_shared_window_per_address(self):
        """/masar and /driver charge the SAME key -- an attacker cannot double the
        entry budget by alternating the two."""
        name = self._arm(cmd="")
        with self._token_reads(), mock.patch.object(
            masar_page, "get_csrf_token", return_value="csrf"
        ), mock.patch.object(driver_page, "get_csrf_token", return_value="csrf"):
            for page, field in ((masar_page, "w"), (driver_page, "d")):
                frappe.local.form_dict[field] = BOGUS
                with self.assertRaises(frappe.Redirect):
                    page.get_context(frappe._dict())
                frappe.local.form_dict.pop(field, None)

        self.assertEqual(self._counter(name), 2)

    def test_every_endpoint_spends_ONE_shared_window_per_address(self):
        """The advertised budget is per IP FULL STOP, not per IP per endpoint.

        frappe's own ``@rate_limit`` welds ``form_dict.cmd`` into its key
        (rate_limiter.py:155) and the REST layer sets cmd to the called method
        (api/v1.py:39), which would hand every guest endpoint a private N. Failures
        split across two DIFFERENT cmd values must trip the SAME ceiling, and a third
        endpoint must find the budget already spent.
        """
        name = self._arm(cmd="a210.endpoint.one")
        half = LIMIT // 2
        with self._token_reads():
            for cmd, attempts in (
                ("a210.endpoint.one", half),
                ("a210.endpoint.two", LIMIT - half),
            ):
                frappe.local.form_dict = frappe._dict({"cmd": cmd})
                for _ in range(attempts):
                    with self.assertRaises(frappe.PermissionError):
                        token_security.resolve_portal_subject(
                            token_security.DRIVER, BOGUS, required=True
                        )
            frappe.local.form_dict = frappe._dict({"cmd": "a210.endpoint.three"})
            with self.assertRaises(frappe.RateLimitExceededError) as raised:
                token_security.resolve_portal_subject(
                    token_security.DRIVER, BOGUS, required=True
                )

        self.assertEqual(getattr(raised.exception, "http_status_code", None), 429)
        self.assertEqual(self._counter(name), LIMIT + 1)

    def test_a_console_or_job_caller_is_never_throttled(self):
        """No request means no address to attribute the attempt to, so a scheduled
        job or a console call resolving a token can never consume a worker's window
        (mirrors rate_limiter.py:134)."""
        name = self._arm()
        frappe.local.request = None
        frappe.local.form_dict = frappe._dict()
        with self._token_reads():
            for _ in range(LIMIT * 2):
                with self.assertRaises(frappe.PermissionError):
                    token_security.resolve_portal_subject(
                        token_security.DRIVER, BOGUS, required=True
                    )

        self.assertEqual(self._counter(name), 0)
