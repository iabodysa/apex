# Copyright (c) 2026, AFMCO and contributors
"""Portal bad-token throttle (A-110), proved in BOTH directions.

A rate limiter nobody proved fires is not hardening; one nobody proved lets real
users through is an outage. These drive the REAL throttle and the REAL cache against
a constructed request, so they need no served site and no fixtures: the only thing
stubbed is the token row lookup, which keeps the whole module DB-write-free.

The counterpart integration coverage in ``apex/tests/test_portal_token_security.py``
exercises the same guard against real ``Masar Worker Token`` rows.

TestThrottleAddressIsolation is the app-wide half (A-220): the window is keyed on
the address alone, so two test files minting from one subnet share a budget and can
red each other at random. It derives every file's subnet FROM THE SOURCE rather than
listing a known pair, so a file added later is covered the day it is written.

TestBadTokenAddressGuard is the A-228 half: ``test_a_console_or_job_caller_is_never_
throttled`` clears the REQUEST, so the first guard returns and the address is never
read -- the second guard had no test that could reach it. That class installs a
request and removes only the address, so the inner guard is the one under test.
"""

import ast
import os
import re
import unittest
from unittest import mock

import frappe

from apex.apex_core.utils import portal_token_security as token_security
from apex.tests.source_tree import (
    parse as _parse,
    rel as _rel,
    test_py_files,
    test_support_files,
)
from apex.www import driver as driver_page, masar as masar_page

_ABSENT = object()

LIMIT = token_security.BAD_TOKEN_ATTEMPTS_PER_MINUTE
BAD_TOKEN_SUBNET = "2001:db8:f10d::"
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


class _RestoresFrappeLocals:
    """Snapshot the request globals a test installs, and put them back EXACTLY.

    ``frappe.local`` is a werkzeug ``Local``: reading an unset name raises and
    iterating does not list it, so ABSENCE IS A VALUE and None is a different state.
    Snapshotting with ``getattr(..., None)`` and restoring by ``setattr`` therefore
    converts unset into None and strands it on a process global — invisible to a
    ``FrappeTestCase`` canary (frappe reads ``request`` with a defaulted getattr) and
    caught only by A-231's snapshot diff, which is how this file became that guard's
    single baseline entry. ``_ABSENT`` keeps the distinction, and both classes below
    share ONE implementation so the two cannot drift apart again.
    """

    LOCALS = ("request", "request_ip", "form_dict")

    def snapshot_frappe_locals(self):
        saved = {name: getattr(frappe.local, name, _ABSENT) for name in self.LOCALS}
        self.addCleanup(self._restore_frappe_locals, saved)

    @staticmethod
    def _restore_frappe_locals(saved):
        for name, previous in saved.items():
            if previous is _ABSENT:
                if hasattr(frappe.local, name):
                    delattr(frappe.local, name)
            else:
                setattr(frappe.local, name, previous)


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


class TestPortalTokenThrottle(_RestoresFrappeLocals, unittest.TestCase):
    """Both directions of the failed-token throttle, on a constructed request."""

    def setUp(self):
        self.snapshot_frappe_locals()

    def _arm(self, ip=None, cmd=None, cookies=None):
        """Stand up one request surface and return its throttle key NAME.

        The window is keyed on the ADDRESS ALONE, so a unique address per call is
        what buys a fresh window, and this file's own ``BAD_TOKEN_SUBNET`` is what
        keeps that window out of another test file's reach; ``cmd`` is set only to
        prove the key ignores it. The name handed to the cache is deliberately RAW:
        ``delete_value`` re-applies ``make_key`` (redis_wrapper.py:141-142), so an
        already-made key is prefixed a second time and clears nothing.
        """
        ip = ip or BAD_TOKEN_SUBNET + frappe.generate_hash(length=12)
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
        """No request at all, so a scheduled job or a console call resolving a token
        can never consume a worker's window (mirrors rate_limiter.py:134).

        This clears the REQUEST, which is the limiter's FIRST guard, so the address
        read below it never runs here -- ``TestBadTokenAddressGuard`` is what covers
        that second guard.
        """
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


class TestBadTokenAddressGuard(_RestoresFrappeLocals, unittest.TestCase):
    """A request that carries NO address -- the limiter's SECOND guard.

    ``test_a_console_or_job_caller_is_never_throttled`` removes the request, so the
    first guard returns and the address below it is never read: no test in the file
    could reach the line that decides what to do with a missing address. Here the
    request is PRESENT and only the address is gone, in both shapes it occurs in:
    unset (a bare read raises ``AttributeError``) and None (``frappe.init`` sets it and
    ``frappe.app`` fills it, so None is what every non-HTTP caller carries).

    The window is keyed on the address ALONE (``BAD_TOKEN_WINDOW_KEY``), so a None
    address charges a bucket literally named ``...:None`` -- ONE window shared by every
    addressless caller in the app, which inverts a per-address ceiling into a way for
    any one of them to 429 all the rest.

    ``charge_window`` is spied rather than spent, so what is asserted is the DECISION
    to charge. That needs no site and no Redis: a throttle whose guards can only be
    exercised against a live bench is a throttle whose guards do not get tested.
    """

    def setUp(self):
        self.snapshot_frappe_locals()
        self.charged = []
        spy = mock.patch.object(
            token_security,
            "charge_window",
            side_effect=lambda name, window, limit: self.charged.append(name) or 1,
        )
        spy.start()
        self.addCleanup(spy.stop)
        frappe.local.form_dict = frappe._dict({"cmd": "a228-" + frappe.generate_hash(length=12)})

    def test_a_request_with_no_address_declines_instead_of_charging(self):
        for label, install_none in (("unset", False), ("None", True)):
            with self.subTest(request_ip=label):
                self.charged.clear()
                if hasattr(frappe.local, "request_ip"):
                    delattr(frappe.local, "request_ip")
                if install_none:
                    frappe.local.request_ip = None
                frappe.local.request = _Request()

                self.assertIsNone(token_security._throttle_bad_token_attempt())
                self.assertEqual(
                    self.charged,
                    [],
                    "an addressless caller was charged, so every one of them shares "
                    "a single window and any of them can 429 the rest",
                )

    def test_the_guard_still_charges_a_request_that_has_an_address(self):
        """Non-vacuous: the guard must decline an absent address, not every call.

        Without this, replacing the whole body with ``return`` would pass the test
        above and quietly retire the only ceiling on failed portal tokens. The address
        stays inside this file's own reserved subnet even though a spied charge never
        reaches a shared window.
        """
        frappe.local.request = _Request()
        frappe.local.request_ip = BAD_TOKEN_SUBNET + frappe.generate_hash(length=12)

        token_security._throttle_bad_token_attempt()

        self.assertEqual(
            self.charged,
            [token_security.BAD_TOKEN_WINDOW_KEY.format(frappe.local.request_ip)],
        )


# An address-shaped string LITERAL: an IPv6 form (it carries a ``::``, which a
# ``08:00:00`` clock literal never does) or a four-part IPv4 form whose last part may
# be empty because a file appends the host part itself.
_ADDRESS_SEED = re.compile(
    r"^(?:[0-9a-fA-F:]*::[0-9a-fA-F:]*|\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{0,3})$"
)


def _test_sources():
    """Every test module app-wide PLUS the plain-named shared helpers beside them —
    a fixture promoted into ``tests/factories.py`` mints addresses just as a
    ``test_*.py`` does, so leaving it out would reopen the hole one hop away."""
    return test_py_files() + test_support_files()


def _address_seeds_in(tree):
    """The address-shaped string literals a parsed module carries.

    Anchored, so an address MENTIONED inside a sentence in a docstring is not read as
    a seed; a real seed is the whole literal, because the random host part is
    concatenated onto it.
    """
    return {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and _ADDRESS_SEED.match(node.value)
    }


def _writes_request_ip(tree):
    """True when the module assigns ``frappe.local.request_ip`` — the one move that
    lets a test charge a REAL bad-token window, so the set of files that must own a
    subnet is read off the code instead of being listed by hand."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
            targets = [node.target]
        else:
            continue
        for target in targets:
            if isinstance(target, ast.Attribute) and target.attr == "request_ip":
                return True
    return False


def _scan_test_addresses():
    """``{relpath: (seeds, writes_request_ip)}`` for every scanned test source."""
    scanned = {}
    for path in _test_sources():
        tree = _parse(path)
        if tree is None:
            continue
        scanned[_rel(path)] = (_address_seeds_in(tree), _writes_request_ip(tree))
    return scanned


class TestThrottleAddressIsolation(unittest.TestCase):
    """No two test files may be able to mint the SAME throttle address.

    The bad-token window is keyed on the address alone, so two files drawing from one
    subnet share one budget: whichever runs second finds it spent and reds for a
    reason that is nowhere in its own source. Distinctness used to rest on a 48-bit
    random suffix — safe by birthday odds, but uncheckable by reading either file.

    Pure AST, so it needs no site and no Redis, and it derives each file's subnet from
    that file rather than from a list kept here.
    """

    def test_detector_reads_a_subnet_and_ignores_a_clock_literal(self):
        """Without this the scan could go blind and pass forever.

        The fixture addresses are BUILT, never written as literals here: a bare one
        would become this file's own seed and collide with the file it was copied
        from — which is the very failure the scan exists to report.
        """
        v4 = ".".join(("198", "18", "0", ""))
        tree = ast.parse(
            f'SUBNET = "{BAD_TOKEN_SUBNET}"\n'
            f'GATE = "{":".join(("08", "00", "00"))}"\n'
            f'DOC = "one address, {BAD_TOKEN_SUBNET}1, named inside a sentence"\n'
            f'V4 = "{v4}"\n'
            "frappe.local.request_ip = SUBNET\n"
        )
        self.assertEqual(_address_seeds_in(tree), {BAD_TOKEN_SUBNET, v4})
        self.assertTrue(_writes_request_ip(tree))
        self.assertFalse(_writes_request_ip(ast.parse("frappe.local.request = None\n")))

    def test_scan_still_sees_both_portal_throttle_test_files(self):
        """The two files A-220 pulled apart must stay IN the scan. Their subnets are
        read from source, never named here — only their presence is asserted, so the
        scan cannot go blind on exactly the pair it was written for."""
        scanned = _scan_test_addresses()
        for relpath in (
            os.path.join("tests", "test_portal_token_security.py"),
            os.path.join("apex_core", "utils", "test_portal_token_throttle.py"),
        ):
            self.assertIn(relpath, scanned, f"{relpath} left the scan — repair the glob")
            seeds, writes_ip = scanned[relpath]
            self.assertTrue(writes_ip, f"{relpath} no longer charges a real window")
            self.assertTrue(seeds, f"{relpath} declares no address subnet")

    def test_every_window_charging_test_file_declares_a_subnet(self):
        """A file that installs ``request_ip`` while hardcoding no address at all would
        pass the distinctness check vacuously, so require it to own a subnet."""
        silent = sorted(
            relpath
            for relpath, (seeds, writes_ip) in _scan_test_addresses().items()
            if writes_ip and not seeds
        )
        self.assertEqual(
            silent,
            [],
            "test file(s) charge a real bad-token window from an address this scan "
            "cannot see. Mint the address from a module-level subnet literal so its "
            "isolation is provable by reading the file:\n"
            + "\n".join(f"  {relpath}" for relpath in silent),
        )

    def test_no_two_test_files_can_mint_an_overlapping_address(self):
        """Prefix-freeness ACROSS files, which is stronger than inequality: the host
        part is appended, so as long as no file's subnet is a prefix of another's, no
        suffix either file could draw can make the two addresses equal."""
        scanned = {
            relpath: seeds
            for relpath, (seeds, _writes_ip) in _scan_test_addresses().items()
            if seeds
        }
        overlaps = []
        for left, left_seeds in sorted(scanned.items()):
            for right, right_seeds in sorted(scanned.items()):
                if left >= right:
                    continue
                overlaps += [
                    f"{left} {one!r} vs {right} {other!r}"
                    for one in sorted(left_seeds)
                    for other in sorted(right_seeds)
                    if one.startswith(other) or other.startswith(one)
                ]
        self.assertEqual(
            overlaps,
            [],
            "two test files can mint the same throttle address, so one file's failed "
            "tokens can spend the other's per-address budget. Give each file its own "
            "reserved subnet (RFC 3849 2001:db8::/32, or RFC 5737 for IPv4):\n"
            + "\n".join(f"  {row}" for row in overlaps),
        )


if __name__ == "__main__":
    unittest.main()
