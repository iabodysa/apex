# Copyright (c) 2026, afmcoltd
"""``board_worker`` is an ``allow_guest`` write, so its refusals are what is graded.

The endpoint boards a worker on a driver's trip with ``ignore_permissions`` and no
role behind the caller, so five gates are the whole of its authorization: the portal
kill switch, the actor/trip resolution, the row lock, the manifest membership, and
the duplicate check. The single test that used to live here patched EVERY one of them
out and asserted only the happy path — so each gate could be deleted from the endpoint
and this file stayed green.

Each gate now has a case in which it REFUSES, and each of those asserts that nothing
was written: that is what a deleted gate fails. The happy path is kept as one case
among six rather than as the whole file.

The gates' own internals still stand in for the database — ``_resolve_trip`` resolves
a credential through three tables — but they are no longer invisible: the endpoint has
to call them, pass them the server-resolved values, and stop when they say no.

``_no_request_environment`` is what lets these run without a request at all.
"""

from unittest import TestCase
from unittest.mock import MagicMock, patch

import frappe

from apex.salis.api import manual_boarding


TRIP = "DT-1"
WORKER = "EMP-1"
REQUEST = "TR-1"
RESOLVED_TRIP = {"driver": "DRV-1", "transport_request": REQUEST}


class _Refused(Exception):
    """Whatever a gate raises; the endpoint must let it out untouched."""


def _no_request_environment():
    """Make the endpoint's two decorators inert outside an HTTP request.

    ``frappe.rate_limiter`` returns early when there is no request
    (``frappe/rate_limiter.py:134``) and ``frappe.whitelist``'s argument-type check
    reads ``local.flags.in_test`` (``frappe/__init__.py:843``). Neither name is bound
    off-request, and an unbound werkzeug Local RAISES rather than answering None, so
    each has to be given the value it would hold under the bench suite.
    """
    frappe.local.request = None
    if not hasattr(frappe.local, "flags"):
        frappe.local.flags = frappe._dict(in_test=True)


class _Run:
    """One invocation of ``board_worker`` with every gate observable."""

    def __init__(self, result=None, error=None, log=None, frappe_mock=None, gates=None):
        self.result = result
        self.error = error
        self.log = log
        self.frappe = frappe_mock
        self.gates = gates

    @property
    def wrote_a_boarding(self):
        """True when the endpoint actually boarded someone."""
        return bool(self.log.append.called or self.gates["mark_boarded"].called)

    def audited(self):
        """The ``result`` of each Boarding Scan Log row the endpoint wrote."""
        return [call.args[3] for call in self.gates["log_attempt"].call_args_list]


def _call(
    *,
    employee=WORKER,
    dispatch_trip=TRIP,
    manifest=(WORKER,),
    already_boarded=False,
    enabled_raises=None,
    resolve_raises=None,
):
    log = MagicMock(name="trip_start_log")
    log.name = "LOG-1"
    log.boarded_count = 1

    gates = {
        "require_enabled": MagicMock(side_effect=enabled_raises),
        "resolve_trip": MagicMock(
            side_effect=resolve_raises, return_value=dict(RESOLVED_TRIP)
        ),
        "manifest": MagicMock(return_value=set(manifest)),
        "get_or_create_log": MagicMock(return_value=log),
        "already_boarded": MagicMock(return_value=already_boarded),
        "mark_boarded": MagicMock(),
        "log_attempt": MagicMock(return_value="SCAN-1"),
    }

    frappe_mock = MagicMock()
    frappe_mock.throw.side_effect = _Refused

    _no_request_environment()
    with patch("apex.salis.api.driver_portal._require_enabled", gates["require_enabled"]), patch(
        "apex.salis.api.boarding._resolve_trip", gates["resolve_trip"]
    ), patch(
        "apex.salis.api.boarding._trip_manifest_workers", gates["manifest"]
    ), patch(
        "apex.salis.api.boarding._get_or_create_log", gates["get_or_create_log"]
    ), patch(
        "apex.salis.api.boarding._already_boarded", gates["already_boarded"]
    ), patch(
        "apex.salis.api.boarding_flow.mark_boarded", gates["mark_boarded"]
    ), patch.object(
        manual_boarding, "_log_attempt", gates["log_attempt"]
    ), patch.object(
        manual_boarding, "frappe", frappe_mock
    ), patch.object(
        # The refusal message is resolved through the real translator, which needs a
        # cache; the message text is not what is under test here.
        manual_boarding,
        "_",
        lambda message: message,
    ):
        try:
            result = manual_boarding.board_worker(dispatch_trip, employee)
            error = None
        except Exception as exc:  # the gate's refusal, whatever shape it took
            result, error = None, exc

    return _Run(result=result, error=error, log=log, frappe_mock=frappe_mock, gates=gates)


class TestManualBoardingAuthorization(TestCase):
    def test_the_kill_switch_stops_the_write(self):
        run = _call(enabled_raises=_Refused("portal disabled"))

        self.assertIsInstance(run.error, _Refused)
        self.assertFalse(run.wrote_a_boarding)
        self.assertEqual([], run.audited(), "a refused request must not be audited as one")

    def test_an_unauthorised_actor_stops_the_write(self):
        """``_resolve_trip`` is the only thing standing between a guest and any trip."""
        run = _call(resolve_raises=_Refused("not your trip"))

        self.assertIsInstance(run.error, _Refused)
        run.gates["resolve_trip"].assert_called_once_with(TRIP)
        self.assertFalse(run.wrote_a_boarding)
        self.assertFalse(run.gates["manifest"].called, "the manifest was read anyway")

    def test_the_trip_row_is_locked_before_the_membership_read(self):
        """Without the lock two taps interleave between the read and the append."""
        run = _call()

        run.frappe.db.get_value.assert_called_once_with(
            "Dispatch Trip", TRIP, "name", for_update=True
        )

    def test_a_worker_not_on_the_manifest_is_refused_and_audited(self):
        run = _call(manifest=("EMP-OTHER",))

        self.assertEqual("Wrong Trip", run.result["result"])
        self.assertFalse(run.wrote_a_boarding)
        self.assertEqual(["Wrong Trip"], run.audited())
        self.assertFalse(
            run.gates["get_or_create_log"].called,
            "a refused worker must not even open a Trip Start Log",
        )

    def test_membership_is_judged_on_the_server_resolved_trip(self):
        """The client supplies only a trip id; the request it is checked against comes
        from ``_resolve_trip``, so a caller cannot name a manifest of their choosing."""
        run = _call()

        run.gates["manifest"].assert_called_once_with(REQUEST, TRIP)

    def test_a_blank_worker_is_refused_before_anything_is_read(self):
        run = _call(employee="   ")

        self.assertIsInstance(run.error, _Refused)
        self.assertFalse(run.wrote_a_boarding)
        self.assertFalse(run.gates["manifest"].called)

    def test_a_worker_already_boarded_is_not_boarded_twice(self):
        run = _call(already_boarded=True)

        self.assertEqual("Duplicate", run.result["result"])
        self.assertFalse(run.wrote_a_boarding)
        self.assertEqual(["Duplicate"], run.audited())


class TestManualBoardingFallback(TestCase):
    def test_manual_fallback_reuses_the_canonical_boarding_log(self):
        run = _call()

        run.log.append.assert_called_once()
        self.assertEqual("boarding_events", run.log.append.call_args.args[0])
        self.assertEqual("Manual", run.log.append.call_args.args[1]["method"])
        run.gates["mark_boarded"].assert_called_once_with(TRIP, WORKER, source="Manual")
        self.assertEqual("Valid", run.result["result"])
        self.assertEqual(["Valid"], run.audited())
