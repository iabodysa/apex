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

The window's NAME was the same bug through another door. frappe names it after the
caller's ``cmd`` (rate_limiter.py:155) but resolves the handler separately, so two paths
to one function were two ceilings -- 35 over 61 endpoints. Apex names every window after
the HANDLER now (rate_limit_identity.py); this file grew from the five to all 61.

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
import contextlib
import inspect
import json
import pathlib
import tempfile
import unittest
from unittest import mock

import frappe
import frappe.rate_limiter
import frappe.translate
from frappe.auth import HTTPRequest
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

import apex
from apex.apex_core.utils import rate_limit_identity
from apex.habitat.api import front_desk
from apex.habitat.doctype.arrival_batch import arrival_batch
from apex.habitat.web_form.accommodation_resident_request import (
    accommodation_resident_request as resident_request,
)
from apex.habitat.web_form.arrival_manifest import arrival_manifest

# Both driver-portal spellings of one endpoint, imported as MODULES so this file adds no
# second dotted path of its own: the package (what the SPA calls) and the submodule the
# function is defined in. The shared-window case below drives one function through both.
from apex.salis.api import driver_portal
from apex.salis.api.driver_portal import fuel
from apex.salis.web_form.transport_request import transport_request
from apex.salis.web_form.vehicle_incident import vehicle_incident

# The literal all five carried. Named so a reader can grep it to here, to
# salis/api/test_rate_limit_identity.py (the 38 that went first), and to the budget in
# salis/api/driver_portal/test_driver_portal_csrf.py, which now holds the count at zero across BOTH
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

# The whole metered surface, not just the five carriers above. Pinned so a new endpoint,
# or one that quietly loses its decorator, has to come through here.
RATE_LIMITED_ENDPOINTS = 61

# The driver portal package re-exporting its own submodules. Every one is a live second
# dotted path -- the SPA calls the SHORT name (frontend/driver/src/pages/Fuel.vue:113)
# while the function is defined in the long one -- so they are pinned as EXPECTED rather
# than forbidden. Deleting one breaks the portal; adding one is now free of charge.
DRIVER_PORTAL_RE_EXPORTS = 32

IDENTITY_MODULE = "apex.apex_core.utils.rate_limit_identity"

_ABSENT = object()

# The frame a no-argument call is expected to die in. The window is charged and only THEN
# is the endpoint delegated to (rate_limit_identity.py), so the missing-argument
# TypeError is raised from inside Apex's wrapper, after the counter has already moved.
_LIMITER_FILE = rate_limit_identity.__file__

# The bound each submitter puts on ONE admitted call, pinned here rather than read
# from the endpoint for the same reason DECLARED_CEILINGS is: a test that imports the
# ceiling it is checking agrees with any value, so a widened cap would spend the
# larger allowance and still pass. The manifest's unit is ROWS; the other three cap a
# free-text field in CHARACTERS.
MANIFEST_ROW_CAP = 500
RESIDENT_DESCRIPTION_CAP = 2000
TRANSPORT_PURPOSE_CAP = 2000
INCIDENT_DESCRIPTION_CAP = 4000


def _manifest_call(rows):
    """One manifest submission carrying ``rows`` expected workers.

    ``expected_workers`` goes as a JSON STRING, which is the only shape that arrives
    over the wire: form_dict values are built from the query string and body
    (app.py:302-314), so the endpoint's parse branch is the live one.
    """
    return {
        "building": "BUILDING-CAPTURED",
        "expected_date": "2026-01-01",
        "expected_workers": json.dumps(
            [{"worker_name": f"Worker {index}"} for index in range(rows)]
        ),
    }


def _resident_call(chars):
    return {
        "location_token": "LOCATION-CAPTURED",
        "request_type": "Maintenance",
        "description": "d" * chars,
    }


def _transport_call(chars):
    return {
        "from_location": "ORIGIN-CAPTURED",
        "to_location": "DESTINATION-CAPTURED",
        "pickup_datetime": "2026-01-01 08:00:00",
        "passenger_count": 4,
        "purpose": "p" * chars,
    }


def _incident_call(chars):
    return {
        "incident_type": "Accident",
        "vehicle": "VEHICLE-CAPTURED",
        "incident_date": "2026-01-01",
        "description": "d" * chars,
    }


# Each submitter with the ceiling on what one call may carry and a builder that sizes
# a call to any figure, so the refused call and the accepted one are the SAME call at
# two sizes and nothing but the size can explain the difference.
PAYLOAD_BOUNDS = (
    (arrival_manifest, "submit_arrival_manifest", MANIFEST_ROW_CAP, _manifest_call),
    (resident_request, "submit_resident_request", RESIDENT_DESCRIPTION_CAP, _resident_call),
    (transport_request, "submit_transport_request", TRANSPORT_PURPOSE_CAP, _transport_call),
    (vehicle_incident, "submit_vehicle_incident", INCIDENT_DESCRIPTION_CAP, _incident_call),
)


# The tree the alias scan walks. Taken from the imported package rather than from this
# file's own location, so a run that imported apex from somewhere else -- another
# worktree, a stale editable install -- scans the code it actually imported and cannot
# grade a tree nothing here is testing.
_PACKAGE_ROOT = pathlib.Path(apex.__file__).resolve().parent


def _dotted_module(path):
    """The dotted name frappe would have to be sent to reach this file's module."""
    parts = list(path.resolve().relative_to(_PACKAGE_ROOT).with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(["apex", *parts])


def _rate_limited_endpoints():
    """Every ``@rate_limit``-decorated function in the package, and where it got the
    decorator FROM.

    Parsed, never imported, for the same reason the alias scan is: several modules want
    a site and this has to hold site-free. Only module-level ``def``s are collected --
    that is the only shape ``frappe.get_attr`` can reach (__init__.py:1748-1750).

    Returns ``{dotted_endpoint: module the name ``rate_limit`` was imported from}``. The
    source is the load-bearing half: the whole defence is that the decorator naming the
    window is Apex's and not the framework's, and a module that imports the framework's
    directly has opted every endpoint in it back into per-spelling ceilings.
    """
    endpoints = {}
    for path in sorted(_PACKAGE_ROOT.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        module = _dotted_module(path)
        source = None
        for node in tree.body:
            if not (isinstance(node, ast.ImportFrom) and node.module and not node.level):
                continue
            for imported in node.names:
                if (imported.asname or imported.name) == "rate_limit":
                    source = node.module
        for node in tree.body:
            if not isinstance(node, ast.FunctionDef):
                continue
            for decorator in node.decorator_list:
                func = getattr(decorator, "func", None)
                if isinstance(func, ast.Name) and func.id == "rate_limit":
                    endpoints[f"{module}.{node.name}"] = source
    return endpoints


def _canonical_window(module, name, identity):
    """The window ``module.name`` charges, built here rather than read back from the
    limiter -- a test that asks the code under test for the answer agrees with any."""
    return f"rl:{module.__name__}.{name}:{identity}"


def _module_level_aliases():
    """Every module-level name in the package bound to something defined elsewhere.

    Source is parsed, never imported. Comparing live function objects would mean
    importing every module in the app, several of which want a site, and this has to
    hold as a site-free guard. Parsing loses nothing here because the thing being looked
    for IS the import statement: frappe resolves a request's ``cmd`` by attribute lookup
    on the module the string names (handler.py:294-303 -> __init__.py:1748-1750), and a
    module-level ``from X import f`` is exactly what puts ``f`` among that module's
    attributes. A test module counts like any other -- it ships in the package, so a
    dotted path through one resolves for a caller just as well as any other path.

    Returns ``{second_path: defining_path}``.
    """
    aliases = {}
    for path in sorted(_PACKAGE_ROOT.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        module = _dotted_module(path)
        for node in tree.body:
            if isinstance(node, ast.ImportFrom) and node.module and not node.level:
                for imported in node.names:
                    if imported.name != "*":
                        bound = imported.asname or imported.name
                        aliases[f"{module}.{bound}"] = f"{node.module}.{imported.name}"
            elif isinstance(node, ast.Assign) and isinstance(node.value, ast.Name):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        aliases[f"{module}.{target.id}"] = f"{module}.{node.value.id}"
    return aliases


def _relative_imports():
    """Files using a relative import, which the alias scan cannot resolve to a path."""
    offenders = []
    for path in sorted(_PACKAGE_ROOT.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        if any(isinstance(n, ast.ImportFrom) and n.level for n in ast.walk(tree)):
            offenders.append(_dotted_module(path))
    return offenders


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
        (typing_validations.py:88) and the window is charged BEFORE the endpoint is
        delegated to (rate_limit_identity.py), so the missing-argument TypeError lands
        only after the counter has already moved -- and no document is ever inserted.

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
            # Both must hold: raised from the charging wrapper's own frame (so the
            # endpoint body was never entered) AND naming an unbound parameter. Either
            # alone would let a TypeError from INSIDE it read as a healthy call; both
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
                shared = _canonical_window(module, name, _STUB_IP)
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
                shared = _canonical_window(module, name, _STUB_IP)
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

    def test_the_two_live_spellings_of_a_driver_endpoint_share_one_window(self):
        """The real production pair, spent through both names against one ceiling.

        Not a synthetic second path: ``apex.salis.api.driver_portal.submit_fuel_request``
        is what the SPA sends (frontend/driver/src/pages/Fuel.vue:113) and
        ``...driver_portal.fuel.submit_fuel_request`` is where the function is defined,
        so both resolve and both are live. Under the framework's own naming this admitted
        20 against a ceiling of 10; the control below still measures exactly that, so a
        pass here cannot be the fake cache being generous.

        The spellings are asserted to reach the SAME object first -- two windows for two
        DIFFERENT functions would be correct, and would otherwise look identical here.
        """
        self.assertIs(driver_portal.submit_fuel_request, fuel.submit_fuel_request)
        endpoint = driver_portal.submit_fuel_request
        limit = _declared_limits(fuel, "submit_fuel_request")["limit"]
        spellings = (
            "apex.salis.api.driver_portal.submit_fuel_request",
            "apex.salis.api.driver_portal.fuel.submit_fuel_request",
        )
        admitted = 0
        cache = _FakeCache()
        with mock.patch.object(frappe, "cache", cache):
            for spelling in spellings:
                for _ in range(limit + 1):
                    if self._spend_one(endpoint, spelling) is not None:
                        break
                    admitted += 1
                # The caller's own spelling has to be back before the endpoint body sees
                # it: the substitution is a write to frappe.local.form_dict, a process
                # global no transaction rolls back.
                self.assertEqual(frappe.local.form_dict["cmd"], spelling)

        self.assertEqual(
            admitted,
            limit,
            f"submit_fuel_request admitted {admitted} against its ceiling of {limit}: "
            "the second dotted path still buys a window of its own",
        )
        self.assertEqual(
            cache.charged(),
            {_canonical_window(fuel, "submit_fuel_request", _STUB_IP)},
            "the window is not named after the handler both spellings resolve to",
        )

    def test_the_framework_alone_would_still_hand_each_spelling_a_full_window(self):
        """The control: why the Apex decorator exists at all, measured not asserted.

        A function metered by ``frappe.rate_limiter.rate_limit`` directly, driven through
        the same fake cache and the same two spellings, must still admit ``limit`` twice
        and open two windows. Without this, the case above passes just as well if the
        fake stopped counting, and the day frappe keys its own bucket on the resolved
        handler this is the test that reds and retires the Apex decorator deliberately
        rather than by assumption.
        """
        limit = 3

        @frappe.rate_limiter.rate_limit(limit=limit, seconds=60)
        def framework_keyed_endpoint():
            return None

        spellings = ("apex.a294.first.spelling", "apex.a294.second.spelling")
        admitted = 0
        cache = _FakeCache()
        with mock.patch.object(frappe, "cache", cache):
            for spelling in spellings:
                for _ in range(limit + 1):
                    frappe.local.form_dict = frappe._dict({"cmd": spelling})
                    try:
                        framework_keyed_endpoint()
                    except frappe.RateLimitExceededError:
                        break
                    admitted += 1

        self.assertEqual(admitted, limit * 2)
        self.assertEqual(
            cache.charged(),
            {f"rl:{spelling}:{_STUB_IP}" for spelling in spellings},
            "the framework limiter stopped naming its window after the caller's cmd",
        )

    @contextlib.contextmanager
    def _behind_an_appending_edge(self, claim):
        """Let frappe resolve ``request_ip`` from a header, instead of stubbing it.

        The edge modelled is the appending one, which is what nginx's stock
        ``$proxy_add_x_forwarded_for`` builds: the caller's claim arrives FIRST and the
        real peer behind it. ``set_request_ip`` is the installed framework's own
        (auth.py:64-75), so this cannot drift from the precedence frappe follows.
        """
        environ = EnvironBuilder(
            path="/api/method/submit",
            method="POST",
            environ_base={"REMOTE_ADDR": ADDRESS_SUBNET + "7"},
            headers={"X-Forwarded-For": f"{claim}, {ADDRESS_SUBNET}7"},
        ).get_environ()
        saved = [(name, getattr(frappe.local, name, _ABSENT)) for name in ("request", "request_ip")]
        frappe.local.request = Request(environ)
        try:
            HTTPRequest.set_request_ip(HTTPRequest.__new__(HTTPRequest))
            yield frappe.local.request_ip
        finally:
            for name, previous in saved:
                if previous is _ABSENT:
                    if hasattr(frappe.local, name):
                        delattr(frappe.local, name)
                else:
                    setattr(frappe.local, name, previous)

    def test_a_forged_forwarded_claim_mints_a_fresh_window_per_address(self):
        """The other half of the bucket name, taken from the framework not from a stub.

        Every other case in this file installs ``request_ip`` directly. That is honest
        about what is under test, but it quietly assumes the value is the server's to
        decide, and it is not: frappe fills it from the FIRST X-Forwarded-For entry
        (auth.py:64-75), an appending edge puts the caller's claim first, and the bucket
        is ``rl:{cmd}:{request_ip}`` (rate_limiter.py:155). Composed, those three make
        the ceiling per CLAIMED address rather than per caller, so the whole limit rests
        on the deployment overwriting that header -- the thing request_ip_trust.py
        exists to measure and no app-side code can enforce.

        Both claims come from this file's declared subnet, so the app-wide guard on
        address isolation between test files still reads one seed here.
        """
        module, name = GUEST_SUBMITTERS[0]
        endpoint = getattr(module, name)
        limit = DECLARED_CEILINGS[name]
        cmd = f"a294-forwarded-{name}"
        claims = (ADDRESS_SUBNET + "aa", ADDRESS_SUBNET + "bb")
        admitted = 0
        cache = _FakeCache()
        with mock.patch.object(frappe, "cache", cache):
            for claim in claims:
                with self._behind_an_appending_edge(claim) as resolved:
                    self.assertEqual(
                        resolved, claim, "frappe did not take the caller's claim first"
                    )
                    for _ in range(limit + 1):
                        if self._spend_one(endpoint, cmd) is not None:
                            break
                        admitted += 1

        self.assertEqual(
            admitted,
            limit * 2,
            f"{name} did not admit a full {limit} under each forged address",
        )
        self.assertEqual(
            cache.charged(),
            {_canonical_window(module, name, claim) for claim in claims},
        )

    def test_every_metered_endpoint_in_the_package_is_keyed_on_its_own_identity(self):
        """All 61, not just the five above: none may take the framework's decorator.

        This is the whole defence in one assertion. A module that writes
        ``from frappe.rate_limiter import rate_limit`` names its windows after the
        caller's ``cmd`` again (rate_limiter.py:155), so every endpoint in it goes back
        to one ceiling per spelling -- and the driver portal publishes a second spelling
        for 32 of them by design, so the regression would be live on arrival rather than
        latent.

        The count is pinned as well as the source: an endpoint that quietly loses its
        decorator leaves this scan silently, and a shrinking population would otherwise
        read as a clean one.
        """
        endpoints = _rate_limited_endpoints()

        self.assertIn(
            "apex.salis.api.driver_portal.fuel.submit_fuel_request",
            endpoints,
            "the scan missed an endpoint this file drives by hand, so an all-clear below "
            "would mean a broken scan rather than a clean package",
        )
        self.assertEqual(
            len(endpoints),
            RATE_LIMITED_ENDPOINTS,
            f"the metered surface moved from {RATE_LIMITED_ENDPOINTS} to "
            f"{len(endpoints)} endpoints without this guard being told",
        )

        framework_keyed = sorted(
            f"{endpoint} (rate_limit from {source})"
            for endpoint, source in endpoints.items()
            if source != IDENTITY_MODULE
        )
        self.assertEqual(
            framework_keyed,
            [],
            "endpoint(s) metered on the caller-supplied cmd instead of the resolved "
            f"handler; import rate_limit from {IDENTITY_MODULE}:\n"
            + "\n".join(framework_keyed),
        )

    def test_every_second_dotted_path_reaches_an_identity_keyed_endpoint(self):
        """Extended from the four submitters to all 61 metered endpoints.

        The whole package is scanned, not just the defining modules: a second path is
        created by whoever IMPORTS the function, so the evidence has to come from
        everywhere a module-level import can appear -- a package ``__init__`` re-export,
        or a test module that imports the endpoint instead of its module. A test module
        counts like any other; it ships in the package, so a ``cmd`` through one resolves
        for a caller just as well.

        Second paths are no longer forbidden. They are ENUMERATED, and every one has to
        land on an endpoint the case above has already proved is keyed on its handler.
        The 32 that exist are the driver portal package re-exporting its own submodules
        while the SPA calls the short name, so both spellings are production and neither
        can be deleted -- pinning the count is what makes this a ratchet in both
        directions: a 33rd is free of charge but must be seen, and a missing one means
        the portal just lost an endpoint.
        """
        endpoints = _rate_limited_endpoints()
        aliases = _module_level_aliases()

        self.assertIn(
            "apex.apex_core.utils.test_submit_rate_limit_identity.arrival_batch",
            aliases,
            "the scan did not record this file's own module-level import, so an empty "
            "result below would mean a broken scan rather than a clean package",
        )
        self.assertEqual(
            _relative_imports(),
            [],
            "a relative import cannot be resolved to a dotted path, so the scan would "
            "no longer see every second path the package publishes",
        )

        second_paths = {
            alias: target for alias, target in aliases.items() if target in endpoints
        }
        unguarded = sorted(
            f"{alias} -> {target}"
            for alias, target in second_paths.items()
            if endpoints[target] != IDENTITY_MODULE
        )
        self.assertEqual(
            unguarded,
            [],
            "endpoint(s) reachable under a second dotted path AND metered on the "
            "caller's cmd, so each path carries its own full window:\n"
            + "\n".join(unguarded),
        )

        outside_the_portal = sorted(
            alias
            for alias in second_paths
            if not alias.startswith("apex.salis.api.driver_portal.")
        )
        self.assertEqual(
            outside_the_portal,
            [],
            "a second dotted path appeared outside the driver portal's known "
            "re-exports:\n" + "\n".join(outside_the_portal),
        )
        self.assertEqual(
            len(second_paths),
            DRIVER_PORTAL_RE_EXPORTS,
            f"the driver portal published {len(second_paths)} re-exports, not "
            f"{DRIVER_PORTAL_RE_EXPORTS}; the SPA calls these names directly",
        )

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
                shared = _canonical_window(module, name, _STUB_IP)
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


class _CapturedDocument:
    """Stands in for ``frappe.get_doc`` so an accepted call is provable with no database.

    A refusal is easy to observe; an ACCEPTANCE is the half that normally needs a site,
    because the endpoint's last act is an insert. Recording the document the endpoint
    built, and the insert it asked for, makes "the cap let this through" an assertion
    about the write that would have happened rather than about the absence of a throw.
    """

    name = "CAPTURED-DOCUMENT"
    anonymous_tracking_code = "CAPTURED-TRACKING-CODE"

    def __init__(self):
        self.built = []
        self.inserted = 0

    def __call__(self, payload):
        self.built.append(payload)
        return self

    def insert(self, **kwargs):
        self.inserted += 1
        return self


class TestOneCallIsBoundedOnWhatItInserts(unittest.TestCase):
    """The call ceiling and the payload ceiling are different levers, spent here.

    Five calls a minute per address says nothing about how much ONE of those calls
    carries, and all four submitters insert with ``ignore_permissions=True``, so the
    payload bound is the only thing standing between an admitted call and the queue.

    Both directions are proven for each submitter, because either alone is satisfiable
    by a broken cap: a cap that refuses everything passes the over-the-cap case, and a
    cap that refuses nothing passes the at-the-cap case. The refusal is additionally
    required to NAME its ceiling, since a submitter who cannot see the number cannot
    resize the call, and to land before the document is built rather than after.

    The window is not what is under test, so ``frappe.request`` is left unset and the
    limiter hands the call straight through (rate_limiter.py:134). That is what keeps
    these cases independent: a shared counter would make each one's verdict depend on
    how many calls the case before it happened to spend.
    """

    @classmethod
    def setUpClass(cls):
        if getattr(frappe.local, "initialised", False):
            return
        sites = pathlib.Path(tempfile.mkdtemp())
        (sites / "apps.txt").write_text("frappe\napex\n", encoding="utf-8")
        (sites / "common_site_config.json").write_text("{}", encoding="utf-8")
        frappe.init(site="", sites_path=str(sites))

    def setUp(self):
        self._saved = [(name, getattr(frappe.local, name, _ABSENT)) for name in ("request",)]
        self.addCleanup(self._put_request_state_back)
        translations = mock.patch.object(
            frappe.translate, "get_all_translations", lambda *a, **k: {}
        )
        translations.start()
        self.addCleanup(translations.stop)
        frappe.local.request = None

    def _put_request_state_back(self):
        while self._saved:
            name, previous = self._saved.pop()
            if previous is _ABSENT:
                if hasattr(frappe.local, name):
                    delattr(frappe.local, name)
            else:
                setattr(frappe.local, name, previous)

    def _submit(self, module, name, arguments, captured):
        with mock.patch.object(frappe, "get_doc", captured):
            return getattr(module, name)(**arguments)

    def test_a_call_over_the_cap_is_refused_before_anything_is_built(self):
        """One unit past the ceiling must be refused, and refused EARLY.

        The endpoint's check is what keeps an oversized table from being materialised
        at all; a refusal that arrived from the controller instead would still refuse,
        but only after the row list had been built from whatever the caller sent.
        """
        for module, name, cap, build in PAYLOAD_BOUNDS:
            with self.subTest(endpoint=name, cap=cap):
                captured = _CapturedDocument()
                with self.assertRaises(frappe.ValidationError) as refusal:
                    self._submit(module, name, build(cap + 1), captured)
                self.assertEqual(
                    captured.built, [], f"{name} built a document for a call it refused"
                )
                self.assertEqual(captured.inserted, 0)
                self.assertIn(
                    str(cap),
                    str(refusal.exception),
                    f"{name} refused without naming the ceiling, so a real submitter "
                    "cannot tell how far over the call was",
                )

    def test_a_call_exactly_at_the_cap_is_accepted(self):
        """The other direction: the cap must admit a call that sits exactly on it."""
        for module, name, cap, build in PAYLOAD_BOUNDS:
            with self.subTest(endpoint=name, cap=cap):
                captured = _CapturedDocument()
                self._submit(module, name, build(cap), captured)
                self.assertEqual(
                    captured.inserted,
                    1,
                    f"{name} refused a call sitting exactly on its ceiling",
                )
                self.assertEqual(len(captured.built), 1)

    def test_the_manifest_at_its_cap_inserts_every_row_it_was_sent(self):
        """Accepted has to mean accepted WHOLE.

        A cap enforced by silently dropping the overflow would satisfy both directions
        above and quietly lose a supplier's workers, which is worse than a refusal
        because nothing tells the supplier it happened.
        """
        captured = _CapturedDocument()
        self._submit(
            arrival_manifest,
            "submit_arrival_manifest",
            _manifest_call(MANIFEST_ROW_CAP),
            captured,
        )
        self.assertEqual(len(captured.built[0]["expected_workers"]), MANIFEST_ROW_CAP)

    def test_the_endpoint_cap_and_the_controller_cap_are_one_number(self):
        """Two copies of a ceiling are two ceilings the moment either is edited.

        The endpoint keeps its own pre-insert check on purpose -- it refuses before the
        row list is built -- but it must MIRROR the controller rather than restate it,
        so a cap lowered in one place cannot leave the public form admitting the old
        figure. Identity, not equality: equal literals are exactly the state that drifts.
        """
        self.assertIs(
            arrival_manifest._MAX_EXPECTED_WORKERS, arrival_batch._MAX_EXPECTED_WORKERS
        )
        self.assertEqual(arrival_manifest._MAX_EXPECTED_WORKERS, MANIFEST_ROW_CAP)


if __name__ == "__main__":
    unittest.main()
