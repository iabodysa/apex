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
    FAILING_VERDICTS,
    FORGEABLE,
    FORWARDED_HEADER,
    INCONCLUSIVE,
    NO_HEADER,
    OVERWRITTEN,
    OVERWRITTEN_THEN_APPENDED,
    PASSING_VERDICTS,
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
# An inner hop that appends its own peer behind whatever the outer hop already wrote.
INNER_HOP = REAL_SUBNET + "1"
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

    def test_a_safe_overwrite_then_append_chain_is_not_called_forgeable(self):
        """CLAUSE 2. The caller-facing hop REPLACED the header, so the planted probe is
        gone from every entry; an inner hop then appended its own peer behind that
        replacement. frappe reads the head, which is the replacement, so this chain is
        as safe as a lone overwrite -- grading it by entry count alone reports a
        correctly configured edge as broken and sends the deployer to 'fix' it."""
        with _forwarded_request(f"{REAL_PEER}, {INNER_HOP}") as resolved:
            self.assertEqual(resolved, REAL_PEER, "frappe must still read the head")
            report = classify_forwarding(
                f"{REAL_PEER}, {INNER_HOP}", resolved, probe_planted=True
            )
        self.assertEqual(report["verdict"], OVERWRITTEN_THEN_APPENDED)
        self.assertIs(report["trusted"], True)
        self.assertIs(report["forgeable"], False)
        self.assertIs(report["probe_seen"], False)
        self.assertEqual(report["entries"], [REAL_PEER, INNER_HOP])

    def test_an_appending_chain_in_front_of_the_replacement_still_fails(self):
        """CLAUSE 3. The mirror of the case above and the reason entry count cannot be
        dropped as evidence on its own: here the caller-facing hop APPENDED, so the
        probe rides at the head and frappe resolves it. Same entry count, opposite
        verdict, and the discriminator is the probe rather than the length."""
        report = self._grade(f"{PROBE_ADDRESS}, {REAL_PEER}", probe_planted=True)
        self.assertEqual(report["verdict"], FORGEABLE)
        self.assertIs(report["forgeable"], True)
        self.assertIs(report["trusted"], False)
        self.assertEqual(report["resolved_ip"], PROBE_ADDRESS)

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


class TestNothingUnproveableIsCertified(unittest.TestCase):
    """The shapes that must never reach a passing verdict, however the probe is sent.

    Each asserts ``trusted is False`` with ``assertIs`` on purpose: ``assertFalse``
    accepts 0, "" and None, so a verdict key that had gone missing from the passing
    tuple and started returning None would satisfy it while certifying nothing.
    """

    def test_a_planted_probe_with_no_forwarded_header_never_passes(self):
        """CLAUSE 1. The probe rode in on a header that never reached the app, so
        frappe fell through to REMOTE_ADDR (auth.py:68-72) and NOTHING was learned about
        whether the edge overwrites. Reading the probe's absence as an overwrite here
        confuses 'the edge replaced my claim' with 'the edge deleted the header' -- and
        the second one keys every client in the world onto the proxy's own address, so
        one abuser 429s the entire site. It is an incomplete measurement, not a pass."""
        with _forwarded_request(None) as resolved:
            report = classify_forwarding(None, resolved, probe_planted=True)
        self.assertEqual(report["verdict"], NO_HEADER)
        self.assertIs(report["trusted"], False)
        self.assertNotIn(report["verdict"], PASSING_VERDICTS)
        self.assertEqual(report["entries"], [])

    def test_an_empty_forwarded_header_with_a_probe_never_passes(self):
        """The same hole reached through a header that arrives but carries nothing
        usable: no entry means no evidence, whatever the separators look like."""
        for raw in ("", "   ", " , "):
            with self.subTest(raw=repr(raw)):
                report = classify_forwarding(raw, REAL_PEER, probe_planted=True)
                self.assertEqual(report["verdict"], NO_HEADER)
                self.assertIs(report["trusted"], False)

    def test_a_probe_that_survived_never_passes_whatever_was_resolved(self):
        """CLAUSE 3. Caller-supplied content is sitting in the header the app received,
        which is proof the edge does not sanitise it. The shipped check only looked at
        the RESOLVED address, so this shape -- probe intact in the header, some other
        address resolved -- was certified as an overwrite while ``probe_seen`` was true
        in the very same report. Only a change in frappe's precedence produces it today
        (auth.py:66 takes the head), which is exactly when a stale pass is worst."""
        report = classify_forwarding(PROBE_ADDRESS, REAL_PEER, probe_planted=True)
        self.assertEqual(report["verdict"], FORGEABLE)
        self.assertIs(report["trusted"], False)
        self.assertIs(report["probe_seen"], True)

    def test_a_resolved_address_that_is_not_the_first_entry_is_not_certified(self):
        """Every passing verdict argues from auth.py:66 taking the HEAD entry. If the
        address actually in use is not that entry, something else chose it and the
        argument does not apply, so the check refuses rather than passing on a rule
        nothing is following."""
        report = classify_forwarding(REAL_PEER, FORGED_CLAIM, probe_planted=True)
        self.assertEqual(report["verdict"], INCONCLUSIVE)
        self.assertIs(report["trusted"], False)

    def test_no_verdict_is_both_trusted_and_forgeable(self):
        """The two flags are read independently by whoever automates this, so a verdict
        drifting into both tuples would let one caller pass and the other fail."""
        self.assertEqual(set(PASSING_VERDICTS) & set(FAILING_VERDICTS), set())

    def test_every_verdict_the_classifier_can_emit_carries_a_detail_string(self):
        """The runbook quotes these strings verbatim. A verdict with no detail would
        raise KeyError inside the endpoint, turning the diagnostic into a 500."""
        emitted = set()
        cases = [
            (None, REAL_PEER, True),
            (None, REAL_PEER, False),
            (REAL_PEER, REAL_PEER, True),
            (REAL_PEER, REAL_PEER, False),
            (f"{REAL_PEER}, {INNER_HOP}", REAL_PEER, True),
            (f"{FORGED_CLAIM}, {REAL_PEER}", FORGED_CLAIM, False),
            (PROBE_ADDRESS, PROBE_ADDRESS, True),
            (REAL_PEER, FORGED_CLAIM, True),
        ]
        for raw, resolved, planted in cases:
            report = classify_forwarding(raw, resolved, probe_planted=planted)
            emitted.add(report["verdict"])
            self.assertTrue(report["detail"], f"no detail for {report['verdict']}")
        self.assertEqual(
            emitted,
            {
                OVERWRITTEN,
                OVERWRITTEN_THEN_APPENDED,
                FORGEABLE,
                APPENDED,
                NO_HEADER,
                INCONCLUSIVE,
            },
            "the deployer runbook is written against this exact set of verdict strings",
        )


class TestProbeRecognition(unittest.TestCase):
    """The documentation ranges, read off the module rather than restated."""

    def test_every_declared_documentation_range_is_recognised(self):
        for network in request_ip_trust._DOCUMENTATION_NETWORKS:
            with self.subTest(network=str(network)):
                self.assertTrue(is_documentation_address(str(network[7])))

    def test_the_named_probe_address_is_inside_a_declared_range(self):
        """The runbook's address must stay one the check actually recognises."""
        self.assertTrue(is_documentation_address(PROBE_ADDRESS))

    def test_the_probe_is_recognised_in_the_spellings_edges_write(self):
        """A spelling the check does not recognise is a FALSE PASS, not a near miss:
        an unrecognised probe looks erased, and erasure is what certifies the edge.
        Bracketed IPv6, the ``ip:port`` form some load balancers record, and the
        IPv4-mapped IPv6 rendering of the same address all have to land as the probe."""
        for value in (
            PROBE_ADDRESS,
            f"{PROBE_ADDRESS}:41234",
            f"::ffff:{PROBE_ADDRESS}",
            f"[::ffff:{PROBE_ADDRESS}]:41234",
            "2001:db8::7",
            "[2001:db8::7]:8443",
        ):
            with self.subTest(value=value):
                self.assertIs(is_documentation_address(value), True)

    def test_a_probe_wearing_another_spelling_still_fails_the_deployment(self):
        """The same gap reached through the verdict rather than the predicate: the
        probe survived, so this must fail however the edge chose to render it."""
        for value in (f"{PROBE_ADDRESS}:41234", f"::ffff:{PROBE_ADDRESS}"):
            with self.subTest(value=value):
                report = classify_forwarding(value, value, probe_planted=True)
                self.assertEqual(report["verdict"], FORGEABLE)
                self.assertIs(report["trusted"], False)

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
