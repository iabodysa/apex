# Copyright (c) 2026, AFMCO and contributors
"""The XFF trust boundary, proved against frappe's REAL resolver (A-242).

Two request shapes are built as genuine WSGI environs and pushed through
``frappe.auth.HTTPRequest.set_request_ip`` itself -- the function every per-address
limit in this app ultimately depends on. Nothing here reimplements its precedence, so
the premise cannot quietly stop being true while these stay green.

  correctly configured edge  the proxy REPLACED the client's claim, so the app receives
                             one entry holding the real peer -- the forgery is gone
                             before frappe ever looks
  misconfigured edge         the proxy APPENDED, so the app receives
                             ``<client claim>, <real peer>`` and frappe takes the
                             client's -- ``request_ip`` becomes attacker-chosen

WHAT IS STILL OWED: no proxy runs here. These construct the two headers a correct and a
broken nginx would produce and prove what frappe does with each; they do not prove that
any particular nginx produces them. That demonstration needs a real edge in front of a
real site and is the deployer-run check in ``request_ip_trust``.

``_forwarded_request`` writes ``frappe.local`` and puts it back exactly, including the
unset-versus-None distinction A-231 exists to catch: both names are written before the
restore runs, so the teardown deletes rather than stranding a None on a process global.

Addresses: this file owns ``REAL_SUBNET`` and mints every non-probe address from it, so
its literals stay prefix-free from the subnets other throttle tests reserve. The
documentation-range values are derived from the module's own ``_DOCUMENTATION_NETWORKS``
rather than written out, both to keep the ranges in one place and because ``203.0.113.``
is already reserved by ``tests/test_front_desk_rate_limit.py``.
"""

import contextlib
import unittest
from unittest import mock

import frappe
from frappe.auth import HTTPRequest
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

from apex.apex_core.utils import request_ip_trust
from apex.apex_core.utils.request_ip_trust import (
    APPENDED,
    FORGEABLE,
    FORWARDED_HEADER,
    INCONCLUSIVE,
    NO_HEADER,
    OVERWRITTEN,
    PROBE_ADDRESS,
    classify_forwarding,
    forwarded_entries,
    is_documentation_address,
)

_ABSENT = object()
_TOUCHED = ("request", "request_ip")

# Non-documentation on purpose: these stand in for genuine addresses, so the classifier
# must NOT read one as a planted probe.
REAL_SUBNET = "10.242.0."
REAL_PEER = REAL_SUBNET + "5"
FORGED_CLAIM = REAL_SUBNET + "99"
ENDPOINT = "/api/method/apex.apex_core.utils.request_ip_trust.check_request_ip_trust"


@contextlib.contextmanager
def _forwarded_request(header, peer=REAL_PEER, query=""):
    """Run frappe's own ``set_request_ip`` over one constructed request.

    Yields the ``request_ip`` frappe resolved. ``header`` is what the APP receives
    after the edge has had its way with it, which is the only thing frappe can see.
    """
    environ = EnvironBuilder(
        path=ENDPOINT,
        query_string=query,
        environ_base={"REMOTE_ADDR": peer},
        headers={FORWARDED_HEADER: header} if header is not None else {},
    ).get_environ()
    saved = [(name, getattr(frappe.local, name, _ABSENT)) for name in _TOUCHED]
    frappe.local.request = Request(environ)
    try:
        HTTPRequest.set_request_ip(HTTPRequest.__new__(HTTPRequest))
        yield frappe.local.request_ip
    finally:
        for name, previous in saved:
            if previous is _ABSENT:
                delattr(frappe.local, name)
            else:
                setattr(frappe.local, name, previous)


class TestFrappeResolvesWhateverTheEdgeSends(unittest.TestCase):
    """The premise itself, driven through the installed framework."""

    def test_an_overwriting_edge_erases_a_forged_claim(self):
        """The client forged a claim; the proxy replaced the whole header with the
        real peer, so what frappe resolves is the peer and the forgery never lands."""
        with _forwarded_request(REAL_PEER) as resolved:
            self.assertEqual(resolved, REAL_PEER)

    def test_an_appending_edge_hands_a_forged_claim_straight_through(self):
        """The vulnerability. ``$proxy_add_x_forwarded_for`` appends, so the client's
        claim arrives FIRST and auth.py:65-66 takes exactly that -- the caller has
        chosen its own rate-limit bucket and can pick a fresh one per request."""
        with _forwarded_request(f"{FORGED_CLAIM}, {REAL_PEER}") as resolved:
            self.assertEqual(resolved, FORGED_CLAIM)
            self.assertNotEqual(resolved, REAL_PEER)

    def test_a_probe_survives_an_appending_edge(self):
        """The same path with the documentation-range probe: the server ends up
        believing its client is an address that cannot exist on the wire."""
        with _forwarded_request(f"{PROBE_ADDRESS}, {REAL_PEER}") as resolved:
            self.assertEqual(resolved, PROBE_ADDRESS)

    def test_with_no_forwarded_header_the_transport_peer_is_used(self):
        """auth.py's fallback branch: absent the header, the real connection wins."""
        with _forwarded_request(None) as resolved:
            self.assertEqual(resolved, REAL_PEER)


class TestTheCheckGradesBothDeployments(unittest.TestCase):
    """The verdicts, computed from what frappe actually resolved above."""

    def _grade(self, header, probe_planted=False):
        with _forwarded_request(header) as resolved:
            return classify_forwarding(header, resolved, probe_planted=probe_planted)

    def test_a_correct_edge_passes(self):
        """Non-vacuity: the check must clear a good deployment, not fire on all."""
        report = self._grade(REAL_PEER, probe_planted=True)
        self.assertEqual(report["verdict"], OVERWRITTEN)
        self.assertTrue(report["trusted"])
        self.assertFalse(report["forgeable"])
        self.assertFalse(report["probe_seen"])
        self.assertEqual(report["resolved_ip"], REAL_PEER)

    def test_a_passthrough_edge_fires(self):
        """Nothing overwrote the header, so the probe came back as the client. This is
        the case a mere entry COUNT cannot catch -- one entry, wholly forged."""
        report = self._grade(PROBE_ADDRESS, probe_planted=True)
        self.assertEqual(report["verdict"], FORGEABLE)
        self.assertTrue(report["forgeable"])
        self.assertTrue(report["probe_seen"])
        self.assertEqual(report["resolved_ip"], PROBE_ADDRESS)

    def test_an_appending_edge_fires_even_with_no_probe(self):
        """A second entry is proof on its own: the edge appended, so entry one is the
        client's. Caught passively, without the deployer planting anything."""
        report = self._grade(f"{FORGED_CLAIM}, {REAL_PEER}")
        self.assertEqual(report["verdict"], APPENDED)
        self.assertTrue(report["forgeable"])
        self.assertEqual(report["entries"], [FORGED_CLAIM, REAL_PEER])

    def test_an_appending_edge_is_not_absolved_by_a_passing_probe(self):
        """A multi-entry header stays a FAIL even where the probe did not survive, so
        a stray extra hop cannot be graded away by one lucky measurement."""
        report = self._grade(f"{FORGED_CLAIM}, {REAL_PEER}", probe_planted=True)
        self.assertEqual(report["verdict"], APPENDED)
        self.assertTrue(report["forgeable"])

    def test_one_entry_without_a_probe_refuses_to_guess(self):
        """An overwriting proxy and a directly exposed app are the SAME shape here.
        Reporting either verdict would be a coin flip, so it reports neither."""
        report = self._grade(REAL_PEER)
        self.assertEqual(report["verdict"], INCONCLUSIVE)
        self.assertFalse(report["trusted"])
        self.assertFalse(report["forgeable"])

    def test_a_missing_header_is_reported_as_incomplete(self):
        """Not forgeable, but if a proxy IS in front then every client shares its
        address and the per-address ceiling becomes a global outage switch."""
        report = self._grade(None)
        self.assertEqual(report["verdict"], NO_HEADER)
        self.assertFalse(report["trusted"])
        self.assertEqual(report["entries"], [])


class TestProbeRecognition(unittest.TestCase):
    """The documentation ranges, read off the module rather than restated."""

    def test_every_declared_documentation_range_is_recognised(self):
        for network in request_ip_trust._DOCUMENTATION_NETWORKS:
            with self.subTest(network=str(network)):
                self.assertTrue(is_documentation_address(str(network[7])))

    def test_the_named_probe_address_is_inside_a_declared_range(self):
        """The runbook's address must stay one the check actually recognises."""
        self.assertTrue(is_documentation_address(PROBE_ADDRESS))

    def test_a_real_address_is_not_mistaken_for_a_probe(self):
        """Without this the check would grade every deployment FORGEABLE."""
        for value in (REAL_PEER, FORGED_CLAIM, "not-an-address", "", None):
            with self.subTest(value=value):
                self.assertFalse(is_documentation_address(value))

    def test_entries_are_split_and_trimmed_the_way_a_proxy_writes_them(self):
        self.assertEqual(forwarded_entries(f" {FORGED_CLAIM} , {REAL_PEER} "),
                         [FORGED_CLAIM, REAL_PEER])
        self.assertEqual(forwarded_entries(None), [])
        self.assertEqual(forwarded_entries(" , "), [])


class TestTheEndpointReportsTheLiveRequest(unittest.TestCase):
    """The reachable surface: gated, and reading the request it is actually serving."""

    def test_the_report_is_gated_on_system_manager(self):
        """Behavioural, not a source grep: deleting the gate fails this.

        ``frappe.only_for`` returns early under ``flags.in_test`` (frappe/__init__.py:
        943), so asserting a non-manager is REFUSED would pass with no gate at all.
        What is asserted instead is that the gate is consulted, and with which role.
        """
        with mock.patch.object(request_ip_trust.frappe, "only_for") as gate:
            with _forwarded_request(REAL_PEER):
                request_ip_trust.check_request_ip_trust()
        gate.assert_called_once_with("System Manager")

    def test_the_endpoint_grades_the_request_it_is_serving(self):
        """End to end through the whitelisted function: a misconfigured edge is
        reported as forgeable, naming the address the caller chose for itself."""
        header = f"{PROBE_ADDRESS}, {REAL_PEER}"
        with mock.patch.object(request_ip_trust.frappe, "only_for"):
            with _forwarded_request(header, query="probe_planted=1"):
                report = request_ip_trust.check_request_ip_trust(probe_planted="1")

        self.assertEqual(report["verdict"], FORGEABLE)
        self.assertTrue(report["forgeable"])
        self.assertEqual(report["resolved_ip"], PROBE_ADDRESS)

    def test_the_endpoint_is_http_reachable(self):
        """A diagnostic nobody can call is not a control -- importing the module must
        register the dotted path the runbook tells a deployer to curl."""
        self.assertIn(
            request_ip_trust.check_request_ip_trust,
            frappe.whitelisted,
        )


if __name__ == "__main__":
    unittest.main()
