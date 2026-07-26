# Copyright (c) 2026, AFMCO and contributors
"""What the four guest SUBMIT endpoints and the Front Desk scan read COUNT, proven by
spending their real windows.

``@rate_limit``'s ``key`` is not the request attribute it reads like. It is a form_dict
lookup -- ``frappe.form_dict.get(key, "")`` (rate_limiter.py:143) -- over a dict built
from the query string and the body (app.py:302-314), and the identity it feeds is
``<ip>:<user_key>`` (rate_limiter.py:145-150). So ``key="frappe.request.remote_addr"``
never read an address: it read a field no honest caller sends, yielded "", and named a
bucket ``rl:<cmd>:<ip>:``. A caller who DID send that field bought a private window per
value and left the ceiling behind, needing no credential and no proxy misconfiguration.

A-261 closed that on 38 guest driver endpoints (salis/api/test_rate_limit_identity.py).
These five were the tail, and four are the worse half of it: unauthenticated
``allow_guest`` POST endpoints that INSERT a document. A forged window on a read buys
unbounded reads; a forged window on these bought unbounded WRITES -- one Resident
Request, Arrival Batch, Transport Request or Vehicle Incident per call, from any
address, with the honeypot the only thing left standing between a script and the queue.

They now pass no ``key``. ``ip_based`` defaults to True (rate_limiter.py:110) and had
already put the address in the identity (rate_limiter.py:141,147-150), so the ceiling is
unchanged and the caller-chosen suffix is gone.

Nothing here asserts that from the decorator's arguments, which would only restate the
edit. The decorator is parsed for ONE thing: where each ceiling is DECLARED. What gets
asserted is the ceiling frappe ENFORCES, spent call by call, with the attack replayed
WHILE it is spent -- every call rotates the query parameter, so if the parameter still
partitioned, each call would open a fresh window and no refusal could ever arrive.

Hermetic on purpose -- a throttle whose guards only run against a live bench is a
throttle whose guards do not get tested. The counter is a fake in-process cache and the
address is stubbed; the limiter, the identity, the window length and the exception are
frappe's own.

Home: the five endpoints straddle habitat and salis, so neither module's tree is an
honest owner and tests/test_colocation_ratchet.py has the central directory closed. It
sits in the shared kernel beside the other cross-module throttle guards it reasons
about -- rate_window.py, request_ip_trust.py and test_portal_token_throttle.py, which is
the app-wide address-isolation guard this file's subnet answers to.
"""

from __future__ import annotations

import ast
import inspect
import pathlib
import tempfile
import unittest
from unittest import mock

import frappe
import frappe.rate_limiter
import frappe.translate

from apex.habitat.api import front_desk
from apex.habitat.web_form.accommodation_resident_request import (
    accommodation_resident_request as resident_request,
)
from apex.habitat.web_form.arrival_manifest import arrival_manifest
from apex.salis.web_form.transport_request import transport_request
from apex.salis.web_form.vehicle_incident import vehicle_incident

# The literal all five carried. Named so a reader can grep it to here, to
# salis/api/test_rate_limit_identity.py (the 38 that went first), and to the budget in
# tests/test_driver_portal_csrf.py, which now holds the count at zero across BOTH
# populations. Nothing in this file asserts the string is present.
LEGACY_FORM_DICT_KEY = "frappe.request.remote_addr"

# This file's own reserved slice of RFC 3849 documentation space. Every test file that
# installs ``frappe.local.request_ip`` must own a prefix no other file's can be a prefix
# of: the window is keyed on the address alone, so two files drawing from one subnet
# share a budget and whichever runs second reds for a reason nowhere in its own source.
# test_portal_token_throttle.TestThrottleAddressIsolation enforces it app-wide. Taken
# before this file: 203.0.113., 198.51.100., 192.0.2., and the 2001:db8: groups d41e,
# 5ca7, f10d, 5ec0 and 4a71.
ADDRESS_SUBNET = "2001:db8:a294::"
_STUB_IP = ADDRESS_SUBNET + "31"

# The four unauthenticated SUBMIT endpoints, deliberately first: each one inserts a
# document, so the window forged here bought writes rather than reads.
GUEST_SUBMITTERS = (
    (resident_request, "submit_resident_request"),
    (arrival_manifest, "submit_arrival_manifest"),
    (transport_request, "submit_transport_request"),
    (vehicle_incident, "submit_vehicle_incident"),
)

# The Front Desk identifier scan. Session-gated rather than guest, and read-only, so a
# forged window here buys probing rather than writing -- still a bypass, ranked below.
AUTHENTICATED_READS = ((front_desk, "resolve_worker"),)

CARRIERS = GUEST_SUBMITTERS + AUTHENTICATED_READS

# Pinned, so "the declared ceiling is the enforced ceiling" cannot be satisfied by
# moving BOTH: the spending tests read the declaration, so a raised limit would spend
# the larger window and still agree with itself. 5/minute is the published guest-intake
# figure each endpoint's own docstring promises; 60/minute is the Front Desk scan cadence.
DECLARED_CEILINGS = {
    "submit_resident_request": 5,
    "submit_arrival_manifest": 5,
    "submit_transport_request": 5,
    "submit_vehicle_incident": 5,
    "resolve_worker": 60,
}

_ABSENT = object()

# The frappe frame a no-argument call is expected to die in: the limiter charges the
# window and only THEN delegates (rate_limiter.py:132-168), so the missing-argument
# TypeError is raised from inside the limiter's own wrapper, after the counter moved.
_LIMITER_FILE = frappe.rate_limiter.__file__


def _declared_limits(module, name):
    """The ``@rate_limit`` keywords as WRITTEN on ``module.name``.

    Read from source, because a wrapped function no longer carries its decorator's
    arguments. This is the only thing any test here takes from the decorator: which
    ceiling and which window length to then go and spend.
    """
    for node in ast.parse(inspect.getsource(module)).body:
        if not (isinstance(node, ast.FunctionDef) and node.name == name):
            continue
        for decorator in node.decorator_list:
            func = getattr(decorator, "func", None)
            if isinstance(func, ast.Name) and func.id == "rate_limit":
                return {kw.arg: ast.literal_eval(kw.value) for kw in decorator.keywords}
    raise AssertionError(f"{module.__name__}.{name} carries no @rate_limit decorator")


def _whitelist_keywords(module, name):
    """The ``@frappe.whitelist`` keywords as WRITTEN on ``module.name``."""
    for node in ast.parse(inspect.getsource(module)).body:
        if not (isinstance(node, ast.FunctionDef) and node.name == name):
            continue
        for decorator in node.decorator_list:
            func = getattr(decorator, "func", None)
            if isinstance(func, ast.Attribute) and func.attr == "whitelist":
                return {kw.arg: ast.literal_eval(kw.value) for kw in decorator.keywords}
    raise AssertionError(f"{module.__name__}.{name} is not whitelisted")


class _FakeCache:
    """The four calls the limiter makes, plus a ledger of the raw window names it
    charged AND the TTL it opened each one with (rate_limiter.py:152-153) -- the second
    is what lets a test say the window did not WIDEN in time as well as in count."""

    def __init__(self):
        self.counts = {}
        self.ttls = {}

    def make_key(self, key, user=None, shared=False):
        return f"apex-a294|{key}".encode()

    def get(self, key):
        return self.counts.get(key)

    def setex(self, key, seconds, value):
        self.ttls[key] = seconds
        self.counts[key] = value

    def incrby(self, key, value):
        self.counts[key] = int(self.counts.get(key) or 0) + value
        return self.counts[key]

    def charged(self):
        """The raw window names, with the make_key prefix stripped back off."""
        return {key.decode().split("|", 1)[1] for key in self.counts}

    def count(self, name):
        return self.counts.get(f"apex-a294|{name}".encode())

    def ttl(self, name):
        return self.ttls.get(f"apex-a294|{name}".encode())


class _FakeRequest:
    method = "POST"
    cookies: dict = {}
    remote_addr = ADDRESS_SUBNET + "7"


class TestSubmitRateLimitIdentity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Under bench this is already true and init returns early (frappe/__init__.py:197);
        # standalone it binds frappe.local so msgprint can run. Never a site, never a DB.
        if getattr(frappe.local, "initialised", False):
            return
        sites = pathlib.Path(tempfile.mkdtemp())
        (sites / "apps.txt").write_text("frappe\napex\n", encoding="utf-8")
        (sites / "common_site_config.json").write_text("{}", encoding="utf-8")
        frappe.init(site="", sites_path=str(sites))

    def setUp(self):
        self._saved = [
            (name, getattr(frappe.local, name, _ABSENT))
            for name in ("request", "request_ip", "form_dict")
        ]
        self.addCleanup(self._put_request_state_back)
        # frappe.throw renders through _(), which loads translations and reaches for the
        # DB (translate.py:181 -> get_installed_apps -> connect). That is incidental to
        # rate limiting, so it is neutralised; frappe.throw itself, the exception class
        # and its 429 status are all left real.
        translations = mock.patch.object(
            frappe.translate, "get_all_translations", lambda *a, **k: {}
        )
        translations.start()
        self.addCleanup(translations.stop)
        frappe.local.request = _FakeRequest()
        frappe.local.request_ip = _STUB_IP

    def _put_request_state_back(self):
        """Restore EXACTLY, absence included. ``frappe.local`` is a werkzeug Local, so
        an unset name is a different state from None and restoring one as the other
        strands it on a process global that no later test can see it happen."""
        while self._saved:
            name, previous = self._saved.pop()
            if previous is _ABSENT:
                if hasattr(frappe.local, name):
                    delattr(frappe.local, name)
            else:
                setattr(frappe.local, name, previous)

    def _spend_one(self, endpoint, cmd, param=_ABSENT):
        """Issue one request; return the 429 when the limiter refused it, else None.

        The endpoint is invoked with NO arguments. That is deliberate and safe: the
        whitelist wrapper short-circuits its type transform on an empty call
        (typing_validations.py:88) and the limiter charges the window BEFORE delegating
        (rate_limiter.py:132-168), so the missing-argument TypeError lands only after
        the counter has already moved -- and no document is ever inserted.

        The refusal is caught BY NAME, and NOTHING else is tolerated except that one
        argument-binding TypeError -- identified on two independent counts, because a
        bare ``except`` here is the exact bug this file exists not to repeat: the pass
        before this one had a harness report OK at call 121 while every call was raising
        FileNotFoundError, the refusal swallowed alongside it. The bucket ledger cannot
        substitute for this check -- the limiter charges BEFORE it delegates, so a call
        that crashed in the endpoint moves the counter exactly like one that succeeded.
        """
        form_dict = {"cmd": cmd}
        if param is not _ABSENT:
            form_dict[LEGACY_FORM_DICT_KEY] = param
        frappe.local.form_dict = frappe._dict(form_dict)
        try:
            endpoint()
        except frappe.RateLimitExceededError as refusal:
            return refusal
        except TypeError as crash:
            # Both must hold: raised from the limiter's own frame (so the endpoint body
            # was never entered) AND naming an unbound parameter. Either alone would let
            # a TypeError from INSIDE the limiter read as a healthy call; requiring both
            # means a future CPython rewording fails loudly here rather than quietly
            # widening what counts as success.
            frame = crash.__traceback__
            while frame.tb_next is not None:
                frame = frame.tb_next
            if frame.tb_frame.f_code.co_filename != _LIMITER_FILE:
                raise
            if "required positional argument" not in str(crash):
                raise
            return None
        return None

    def test_the_five_carriers_are_all_present_and_still_metered(self):
        """A rename or a dropped decorator must fail here, not pass quietly."""
        self.assertEqual(len(CARRIERS), 5)
        self.assertEqual({name for _module, name in CARRIERS}, set(DECLARED_CEILINGS))
        for module, name in CARRIERS:
            with self.subTest(module=module.__name__, endpoint=name):
                self.assertTrue(callable(getattr(module, name)))
                self.assertEqual(
                    _declared_limits(module, name).get("limit"), DECLARED_CEILINGS[name]
                )

    def test_the_four_guest_submitters_are_still_guest_post_writers(self):
        """Why these four are ranked above the read: the surface that made a forged
        window buy WRITES is still exactly this shape, so the ceiling is the only thing
        bounding it."""
        for module, name in GUEST_SUBMITTERS:
            with self.subTest(module=module.__name__, endpoint=name):
                keywords = _whitelist_keywords(module, name)
                self.assertIs(keywords.get("allow_guest"), True)
                self.assertEqual(keywords.get("methods"), ["POST"])
        for module, name in AUTHENTICATED_READS:
            with self.subTest(module=module.__name__, endpoint=name):
                self.assertIsNot(_whitelist_keywords(module, name).get("allow_guest"), True)

    def test_a_query_parameter_no_longer_buys_a_private_window(self):
        """Three requests differing ONLY in that parameter must share one window."""
        for module, name in CARRIERS:
            with self.subTest(module=module.__name__, endpoint=name):
                cache = _FakeCache()
                cmd = f"a294-share-{name}"
                shared = f"rl:{cmd}:{_STUB_IP}"
                endpoint = getattr(module, name)
                with mock.patch.object(frappe, "cache", cache):
                    for param in (_ABSENT, "alpha", "beta"):
                        self.assertIsNone(
                            self._spend_one(endpoint, cmd, param),
                            f"{name} refused a call well inside its ceiling",
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
                # The keyed shape joined `<ip>` to the lookup, so its bucket ended in a
                # bare colon even when no parameter was sent. That name's ABSENCE is
                # what says the key is gone, rather than merely unused on this call.
                self.assertIsNone(cache.count(f"{shared}:"))

    def test_the_declared_ceiling_is_the_one_enforced_while_the_parameter_rotates(self):
        """Spend each window with a FRESH parameter value on every call.

        This is the attack and the ceiling in one run. If the parameter still
        partitioned, every call would land in its own window and no refusal could
        arrive; the refusal landing on exactly ``limit + 1`` is what says the window did
        not widen, and the ``limit`` calls before it are what say it did not narrow.
        """
        for module, name in CARRIERS:
            limit = _declared_limits(module, name)["limit"]
            with self.subTest(module=module.__name__, endpoint=name, limit=limit):
                cache = _FakeCache()
                cmd = f"a294-ceiling-{name}"
                shared = f"rl:{cmd}:{_STUB_IP}"
                endpoint = getattr(module, name)
                with mock.patch.object(frappe, "cache", cache):
                    for index in range(limit):
                        self.assertIsNone(
                            self._spend_one(endpoint, cmd, f"rotate-{index}"),
                            f"{name} refused call {index + 1} of its {limit} ceiling",
                        )
                    refused = self._spend_one(endpoint, cmd, "rotate-final")

                self.assertIsNotNone(
                    refused,
                    f"{name} admitted call {limit + 1}: a rotating query parameter still "
                    "walks past the ceiling",
                )
                self.assertEqual(getattr(refused, "http_status_code", None), 429)
                self.assertEqual(cache.charged(), {shared})
                self.assertEqual(cache.count(shared), limit + 1)

    def test_the_window_length_is_the_declared_one_and_is_never_refreshed(self):
        """The count ceiling is only half of "did not widen": a window opened for longer
        than 60s, or re-opened mid-flight, would let the same ceiling serve a larger
        burst. The TTL frappe hands redis (rate_limiter.py:152-153) is read back from
        the ledger, and a second call inside the window must not reset it.
        """
        for module, name in CARRIERS:
            declared = _declared_limits(module, name)
            with self.subTest(module=module.__name__, endpoint=name):
                cache = _FakeCache()
                cmd = f"a294-window-{name}"
                shared = f"rl:{cmd}:{_STUB_IP}"
                endpoint = getattr(module, name)
                with mock.patch.object(frappe, "cache", cache):
                    self._spend_one(endpoint, cmd, "first")
                    self.assertEqual(cache.ttl(shared), declared["seconds"])
                    cache.ttls[cache.make_key(shared)] = "not-reopened"
                    self._spend_one(endpoint, cmd, "second")

                self.assertEqual(
                    cache.ttl(shared),
                    "not-reopened",
                    f"{name} re-opened its window mid-flight, so the ceiling covers a "
                    "rolling period rather than a fixed one",
                )
                self.assertEqual(declared["seconds"], 60)


if __name__ == "__main__":
    unittest.main()
