# Copyright (c) 2026, AFMCO and contributors
"""What the guest driver endpoints COUNT, proven by spending their real windows.

``@rate_limit``'s ``key`` is not the request attribute it reads like. It is a form_dict
lookup -- ``frappe.form_dict.get(key, "")`` (rate_limiter.py:143) -- over a dict built
from the query string and body (app.py:310-311), and the identity it feeds is
``<ip>:<user_key>`` (rate_limiter.py:147-148). So ``key="frappe.request.remote_addr"``
never read an address: it read a field no honest caller sends, yielded "", and named a
bucket ``rl:<cmd>:<ip>:``. A caller who DID send that field bought a private window per
value and left the ceiling behind entirely -- a full bypass on every deployment, needing
no proxy misconfiguration.

These endpoints now pass no ``key`` at all. ``ip_based`` already put the address in the
identity (rate_limiter.py:141,150), so the ceiling is unchanged and the caller-chosen
suffix is gone.

Asserting that from the decorator's arguments would be vacuous, so nothing here reads
them except to learn where each ceiling is DECLARED; the ceiling that gets asserted is
the one the framework actually ENFORCES, by spending it. The attack is replayed while
it is spent: every call rotates the query parameter, so if it still partitioned, each
call would open a fresh window and the refusal would never arrive.

Hermetic on purpose -- a throttle whose guards only run against a live bench is a
throttle whose guards do not get tested. The counter is a fake in-process cache and the
address is stubbed, but the limiter, the identity, and the exception are frappe's own.
"""

from __future__ import annotations

import ast
import inspect
import pathlib
import tempfile
import unittest
from unittest import mock

import frappe
import frappe.translate

from apex.salis.api import boarding_flow
from apex.salis.api.driver_portal import (
    attendance,
    boarding,
    clearance,
    execution,
    fuel,
    home,
    notifications,
    profile,
    support,
    trips,
)
from apex.salis.api import driver_portal

# The literal every one of these endpoints used to carry. Named so a reader can grep it
# to this file and to the budget in tests/test_driver_portal_csrf.py, which holds it at
# zero; nothing here asserts the string is present.
LEGACY_FORM_DICT_KEY = "frappe.request.remote_addr"

# The guest driver surface: the driver_portal package plus the driver half of
# boarding_flow. salis/api/boarding.py is absent on purpose -- its two endpoints charge
# in the body via rate_window.charge_window, which tests/test_front_desk_rate_limit.py
# spends against a live bench.
MODULES = (
    driver_portal,
    attendance,
    boarding,
    clearance,
    execution,
    fuel,
    home,
    notifications,
    profile,
    support,
    trips,
    boarding_flow,
)

# 38 endpoints carried the legacy key and were de-keyed; boarding_flow's three
# ``worker_*`` endpoints never carried one. The three are kept in scope as the control:
# they always had the shape the other 38 now have, so a regression that reaches all of
# them cannot hide behind "this file only ever tested the ones that were changed".
DE_KEYED_ENDPOINTS = 38
ALREADY_KEYLESS_ENDPOINTS = 3
EXPECTED_ENDPOINTS = DE_KEYED_ENDPOINTS + ALREADY_KEYLESS_ENDPOINTS

_ABSENT = object()

# This file's own reserved slice of RFC 3849 documentation space. Every test file that
# installs frappe.local.request_ip must own a prefix no other file's can be a prefix of,
# because the bad-token window is keyed on the address alone: two files drawing from one
# subnet share one budget, and whichever runs second reds for a reason nowhere in its own
# source. test_portal_token_throttle.TestThrottleAddressIsolation enforces it. The first
# draft here used 203.0.113. and 198.51.100., both already owned by
# tests/test_front_desk_rate_limit.py, and that guard caught it.
ADDRESS_SUBNET = "2001:db8:4a71::"
_STUB_IP = ADDRESS_SUBNET + "29"


def _decorated_endpoints():
    """Every ``@rate_limit``-decorated whitelisted endpoint, with its DECLARED ceiling.

    The module source is parsed rather than the live decorator inspected, because a
    wrapped function no longer carries its arguments. Re-exports in the package
    ``__init__`` are imports, not definitions, so each endpoint is found exactly once.
    """
    found = []
    for module in MODULES:
        tree = ast.parse(inspect.getsource(module))
        for node in tree.body:
            if not isinstance(node, ast.FunctionDef):
                continue
            limits = {}
            whitelisted = False
            for decorator in node.decorator_list:
                if not isinstance(decorator, ast.Call):
                    continue
                func = decorator.func
                name = func.attr if isinstance(func, ast.Attribute) else func.id
                if name == "whitelist":
                    whitelisted = True
                elif name == "rate_limit":
                    limits = {
                        keyword.arg: ast.literal_eval(keyword.value)
                        for keyword in decorator.keywords
                    }
            if whitelisted and limits:
                found.append((module, node.name, limits))
    return found


class _FakeCache:
    """The four calls the limiter makes, plus a ledger of the raw names it charged."""

    def __init__(self):
        self.counts = {}

    def make_key(self, key, user=None, shared=False):
        return f"apex-test|{key}".encode()

    def get(self, key):
        return self.counts.get(key)

    def setex(self, key, seconds, value):
        self.counts[key] = value

    def incrby(self, key, value):
        self.counts[key] = int(self.counts.get(key) or 0) + value
        return self.counts[key]

    def charged(self):
        """The raw window names, with the make_key prefix stripped back off."""
        return {key.decode().split("|", 1)[1] for key in self.counts}

    def count(self, name):
        return self.counts.get(f"apex-test|{name}".encode())


class _FakeRequest:
    method = "GET"
    cookies: dict = {}
    remote_addr = ADDRESS_SUBNET + "7"


class TestGuestDriverRateLimitIdentity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Under bench this is already true and init returns early (frappe/__init__.py:197);
        # standalone it binds frappe.local so msgprint can run. Never a site, never a DB.
        # The throwaway sites dir carries only what init reads: apps.txt, for the module
        # map (frappe/__init__.py:1532), and an empty common config.
        if getattr(frappe.local, "initialised", False):
            return
        sites_path = pathlib.Path(tempfile.mkdtemp())
        (sites_path / "apps.txt").write_text("frappe\napex\n", encoding="utf-8")
        (sites_path / "common_site_config.json").write_text("{}", encoding="utf-8")
        frappe.init(site="", sites_path=str(sites_path))

    def setUp(self):
        self.endpoints = _decorated_endpoints()
        self._saved = {
            name: getattr(frappe.local, name, _ABSENT)
            for name in ("request", "request_ip", "form_dict")
        }
        self.addCleanup(self._restore)
        # frappe.throw renders its message through _(), which loads translations and
        # reaches for the DB (translate.py:181 -> get_installed_apps -> connect). That is
        # incidental to rate limiting, so it is neutralised; frappe.throw itself, the
        # exception class, and its 429 status are all left real.
        patch = mock.patch.object(frappe.translate, "get_all_translations", lambda *a, **k: {})
        patch.start()
        self.addCleanup(patch.stop)
        frappe.local.request = _FakeRequest()
        frappe.local.request_ip = _STUB_IP

    def _restore(self):
        for name, previous in self._saved.items():
            if previous is _ABSENT:
                if hasattr(frappe.local, name):
                    delattr(frappe.local, name)
            else:
                setattr(frappe.local, name, previous)

    def _call(self, endpoint, cmd, param=_ABSENT):
        """Issue one request; return the 429 if the limiter refused it, else None.

        Endpoints are called with no arguments: the decorator's wrapper takes ``*args``
        and charges the window BEFORE delegating (rate_limiter.py:132-168), so the
        TypeError from the missing arguments lands after the counter has already moved.
        Every non-refusal exception is classified and discarded rather than swallowed by
        a bare except, so a crash can never be read as a call that was allowed.
        """
        form_dict = {"cmd": cmd}
        if param is not _ABSENT:
            form_dict[LEGACY_FORM_DICT_KEY] = param
        frappe.local.form_dict = frappe._dict(form_dict)
        try:
            endpoint()
        except frappe.RateLimitExceededError as exc:
            return exc
        except BaseException:
            return None
        return None

    def test_the_guest_driver_surface_is_covered_in_full(self):
        """A rename that drops an endpoint out of this file must fail, not pass quietly."""
        self.assertEqual(len(self.endpoints), EXPECTED_ENDPOINTS)

    def test_a_query_parameter_no_longer_buys_a_private_window(self):
        """Three requests differing ONLY in that parameter must share one window."""
        for module, name, limits in self.endpoints:
            with self.subTest(module=module.__name__, endpoint=name):
                cache = _FakeCache()
                cmd = f"a261-share-{name}"
                shared = f"rl:{cmd}:{_STUB_IP}"
                with mock.patch.object(frappe, "cache", cache):
                    for param in (_ABSENT, "alpha", "beta"):
                        self.assertIsNone(
                            self._call(getattr(module, name), cmd, param),
                            f"{name} refused a call well inside its {limits['limit']} ceiling",
                        )

                self.assertEqual(
                    cache.charged(),
                    {shared},
                    f"{name} charged more than the one address window",
                )
                self.assertEqual(cache.count(shared), 3)
                for param in ("alpha", "beta"):
                    self.assertIsNone(
                        cache.count(f"{shared}:{param}"),
                        f"{name} still opens the per-value bucket rl:<cmd>:<ip>:{param}",
                    )
                # The keyed shape charged `<ip>` joined to the lookup, so the bucket ended
                # in a bare colon even when no parameter was sent. Its absence is what
                # says the key is gone rather than merely unused on this call.
                self.assertIsNone(cache.count(f"{shared}:"))

    def test_the_declared_ceiling_is_the_one_enforced_while_the_parameter_rotates(self):
        """Spend each window with a fresh parameter value every call.

        This is the attack and the ceiling in one run. If the parameter still
        partitioned, every call would land in its own window and no refusal could ever
        arrive; the refusal landing on exactly ``limit + 1`` is what says the window did
        not widen, and the ``limit`` calls before it are what say it did not narrow.
        """
        for module, name, limits in self.endpoints:
            limit = limits["limit"]
            with self.subTest(module=module.__name__, endpoint=name, limit=limit):
                cache = _FakeCache()
                cmd = f"a261-ceiling-{name}"
                shared = f"rl:{cmd}:{_STUB_IP}"
                endpoint = getattr(module, name)
                with mock.patch.object(frappe, "cache", cache):
                    for index in range(limit):
                        self.assertIsNone(
                            self._call(endpoint, cmd, f"rotate-{index}"),
                            f"{name} refused call {index + 1} of its {limit} ceiling",
                        )
                    refused = self._call(endpoint, cmd, "rotate-final")

                self.assertIsNotNone(
                    refused,
                    f"{name} admitted call {limit + 1}: a rotating query parameter still "
                    "walks past the ceiling",
                )
                self.assertEqual(getattr(refused, "http_status_code", None), 429)
                self.assertEqual(cache.charged(), {shared})
                self.assertEqual(cache.count(shared), limit + 1)


if __name__ == "__main__":
    unittest.main()
