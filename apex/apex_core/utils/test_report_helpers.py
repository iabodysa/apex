# Copyright (c) 2026, AFMCO and contributors
"""Unit guards for apex_core.utils.report_helpers.

Pure-Python (no live site). Two layers:

* :class:`TestDateRangeCondition` pins the helper's own four-way return contract,
  including a frozen oracle for the verbatim if/elif/elif block it replaced.
* :class:`TestReportsQueryWithTheDateCondition` drives the SHIPPED ``execute()`` of
  three reports that consume the helper and asserts the ``filters`` dict each one
  actually hands ``frappe.get_all``.

The second class replaces a hand-copied mirror of those ``execute()`` bodies.
A mirror is a source-text guard wearing a behavioural costume: it asserted
that a private copy of the filter-building code produced the expected dict, so no
change to the report could ever move it, and it had already drifted — the copy of
``vehicle_utilisation`` carried a ``pre-scope`` note and reproduced neither the
project-scope branch that OVERWRITES ``vehicle`` nor the DocType-existence
short-circuit that returns before the query. Updating the copy would only have
reset the clock on the same defect, so the copy is gone and the real function runs
instead.

Running the real ``execute()`` without a site means replacing the framework EDGES it
touches — translation, session, ``frappe.db``, the project-scope helper, the query
itself — and nothing else. Every line that decides what goes into the filters dict is
the shipped one, so breaking it reds these tests. The stubs go on the ``frappe``
MODULE via ``mock.patch``, never on ``frappe.local``, so nothing is stranded for a
later test module.

Size note: 136 test lines against 13 in the subject (10.5x), for 11 distinct behaviours. The ratio is arithmetic on a small subject, not overtesting: each test names a different behaviour.
"""

import contextlib
import types
import unittest
from unittest.mock import MagicMock, patch

import frappe

from apex.apex_core.utils.report_helpers import date_range_condition
from apex.habitat.report.lease_expiry_watchlist import lease_expiry_watchlist as R_lease
from apex.salis import permissions as SP
from apex.salis.report.fleet_payment_register import fleet_payment_register as R_payments
from apex.salis.report.vehicle_utilisation import vehicle_utilisation as R_utilisation

# (restrict, allowed) as permissions.report_project_scope returns it for a caller
# holding an oversight role — the branch that leaves the report's own filters alone.
UNSCOPED = (False, None)


def _legacy_fragment(filters, from_key="from_date", to_key="to_date"):
    """The exact fragment the inline if/elif/elif blocks produced (oracle).

    Legitimately a frozen copy, unlike a hand-copied report-body mirror:
    it is the SPEC the extracted helper has to preserve, it is compared against the
    shipped ``date_range_condition``, and the code it copies no longer exists to
    drift from.
    """
    if filters.get(from_key) and filters.get(to_key):
        return ["between", [filters[from_key], filters[to_key]]]
    elif filters.get(from_key):
        return [">=", filters[from_key]]
    elif filters.get(to_key):
        return ["<=", filters[to_key]]
    return None


def _passthrough(msg, *args, **kwargs):
    """Stand-in for frappe._ / the module-level _ — column labels are not under test."""
    return msg


def query_filters(report, filters, scope=UNSCOPED, in_scope=()):
    """Run the shipped ``report.execute(filters)`` and return what it queried with.

    Only site-bound edges are stubbed. Two of them are patched on the report module
    rather than on ``frappe`` because the report bound the name at import
    (``from frappe import _``, ``from frappe.utils import today``), and ``today()``
    runs unconditionally after the query, so a stub is what keeps this site-free.
    They are applied only where the module actually holds the name, so a report that
    stops importing one silently loses nothing but the stub.
    """
    get_all = MagicMock(return_value=[])
    edges = [
        patch.object(frappe, "_", _passthrough),
        patch.object(frappe, "get_all", get_all),
        patch.object(frappe, "session", types.SimpleNamespace(user="probe@example.com")),
        # vehicle_utilisation short-circuits when its source DocType is unmigrated.
        patch.object(frappe, "db", types.SimpleNamespace(exists=lambda *a, **k: True)),
        patch.object(SP, "report_project_scope", return_value=scope),
    ]
    if hasattr(report, "_"):
        edges.append(patch.object(report, "_", _passthrough))
    if hasattr(report, "today"):
        edges.append(patch.object(report, "today", lambda: "2026-01-01"))
    if hasattr(report, "scoped_names"):
        edges.append(patch.object(report, "scoped_names", lambda *a, **k: list(in_scope)))

    with contextlib.ExitStack() as stack:
        for edge in edges:
            stack.enter_context(edge)
        report.execute(filters)

    if not get_all.call_args:
        return None
    return get_all.call_args.kwargs["filters"]


class TestDateRangeCondition(unittest.TestCase):
    def test_both_bounds(self):
        f = {"from_date": "2026-01-01", "to_date": "2026-01-31"}
        self.assertEqual(
            date_range_condition(f, "attendance_date"),
            ["between", ["2026-01-01", "2026-01-31"]],
        )

    def test_from_only(self):
        f = {"from_date": "2026-01-01"}
        self.assertEqual(date_range_condition(f, "creation"), [">=", "2026-01-01"])

    def test_to_only(self):
        f = {"to_date": "2026-01-31"}
        self.assertEqual(date_range_condition(f, "log_date"), ["<=", "2026-01-31"])

    def test_neither_returns_none(self):
        self.assertIsNone(date_range_condition({}, "snapshot_date"))
        # empty strings are falsy — same as the original truthiness checks
        self.assertIsNone(date_range_condition({"from_date": "", "to_date": ""}, "creation"))

    def test_custom_keys(self):
        f = {"start": "2026-02-01", "end": "2026-02-28"}
        self.assertEqual(
            date_range_condition(f, "d", from_key="start", to_key="end"),
            ["between", ["2026-02-01", "2026-02-28"]],
        )

    def test_matches_legacy_oracle_all_combos(self):
        combos = [
            {"from_date": "2026-01-01", "to_date": "2026-01-31"},
            {"from_date": "2026-01-01"},
            {"to_date": "2026-01-31"},
            {},
            {"from_date": "", "to_date": "2026-01-31"},
            {"from_date": "2026-01-01", "to_date": ""},
        ]
        for f in combos:
            self.assertEqual(
                date_range_condition(f, "x"),
                _legacy_fragment(f),
                msg=f"diverged from legacy block for filters={f}",
            )


class TestReportsQueryWithTheDateCondition(unittest.TestCase):
    """What three consuming reports really put in their ``frappe.get_all`` filters."""

    def test_probe_reaches_the_query(self):
        """Canary: a probe that never reaches get_all would pass every test below
        by asserting ``None`` against ``None``."""
        for report in (R_payments, R_utilisation, R_lease):
            self.assertIsNotNone(
                query_filters(report, {}),
                f"{report.__name__} did not reach frappe.get_all — the probe's stubs broke",
            )

    def test_fleet_payment_register(self):
        self.assertEqual(
            query_filters(
                R_payments,
                {"status": "Paid", "from_date": "2026-01-01", "to_date": "2026-03-31"},
            ),
            {"status": "Paid", "creation": ["between", ["2026-01-01", "2026-03-31"]]},
        )
        self.assertEqual(query_filters(R_payments, {"company": "AFMCO"}), {"company": "AFMCO"})

    def test_vehicle_utilisation(self):
        self.assertEqual(
            query_filters(R_utilisation, {"from_date": "2026-01-01"}),
            {"snapshot_date": [">=", "2026-01-01"]},
        )
        self.assertEqual(
            query_filters(R_utilisation, {"vehicle": "V-1", "to_date": "2026-06-01"}),
            {"vehicle": "V-1", "snapshot_date": ["<=", "2026-06-01"]},
        )
        self.assertEqual(query_filters(R_utilisation, None), {})

    def test_lease_expiry_watchlist(self):
        self.assertEqual(
            query_filters(R_lease, {}),
            {"docstatus": 1, "status": ["in", ["Approved", "Active"]]},
        )
        self.assertEqual(
            query_filters(
                R_lease,
                {"building": "B-1", "from_date": "2026-01-01", "to_date": "2026-12-31"},
            ),
            {
                "docstatus": 1,
                "status": ["in", ["Approved", "Active"]],
                "building": "B-1",
                "lease_end_date": ["between", ["2026-01-01", "2026-12-31"]],
            },
        )

    def test_no_date_bounds_leaves_the_key_out_of_the_query(self):
        """The helper's None means ABSENT, and the shipped callers honour it.

        Replaces a test that re-typed the caller's ``if frag is not None`` inside
        the test body: a key set to None is not the same query as no key at all
        (an ``is`` / ``is not None`` slip in a report would produce the first), and
        only the real callers can show which one ships.
        """
        for report, key in (
            (R_payments, "creation"),
            (R_utilisation, "snapshot_date"),
            (R_lease, "lease_end_date"),
        ):
            self.assertNotIn(
                key,
                query_filters(report, {}),
                f"{report.__name__} queried on {key} with no from/to bound set",
            )


if __name__ == "__main__":
    unittest.main()
