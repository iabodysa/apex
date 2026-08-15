# Copyright (c) 2026, AFMCO and contributors
"""Trip Boarding Ledger posting engine.

Proves the engine that snapshots each worker's FINAL boarding outcome from the
mutable Trip Boarding State child into an immutable ledger row:

  * post_trip_boarding posts one row per TERMINAL-outcome worker (Boarded /
    Absent) and skips non-terminal rows (Pending / Worker Claimed).
  * the posted row is immutable: an ORM re-save throws PermissionError.
  * posting is idempotent on (dispatch_trip, employee) — re-running posts nothing.
  * reverse_trip_boarding reverse-not-deletes: it posts a mirror (is_cancelled +
    reversal_of) and flags the original is_cancelled, leaving the original intact,
    and is idempotent (no double reversal).

The three workers on the manifest are the shipped Employee fixtures; naming the
dependency is what replaced the ``test_ignore`` block that used to prune the walk behind
their construction. The trip is the subject and is still built here.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.salis.boarding_engine import post_trip_boarding, reverse_trip_boarding

LEDGER = "Trip Boarding Ledger"

test_dependencies = ["Employee"]

WORKERS = ("_Test Employee", "_Test Employee 1", "_Test Employee 2")


class TestTripBoardingLedger(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")

        self.boarded_emp, self.absent_emp, self.pending_emp = (
            frappe.db.get_value("Employee", {"first_name": name}) for name in WORKERS
        )

        self.trip = frappe.get_doc(
            {
                "doctype": "Dispatch Trip",
                "naming_series": "DT-.######",
                "trip_date": "2026-06-20",
                "status": "Planned",
            }
        )
        self.trip.append(
            "boarding_state",
            {"employee": self.boarded_emp, "status": "Boarded", "confirm_source": "Driver"},
        )
        self.trip.append(
            "boarding_state", {"employee": self.absent_emp, "status": "Absent"}
        )
        self.trip.append(
            "boarding_state", {"employee": self.pending_emp, "status": "Pending"}
        )
        self.trip.flags.ignore_validate = True
        self.trip.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)

    def tearDown(self):
        frappe.set_user("Administrator")
        for row in frappe.get_all(
            LEDGER, filters={"dispatch_trip": self.trip.name}, pluck="name"
        ):
            frappe.db.delete(LEDGER, {"reversal_of": row})
        frappe.db.delete(LEDGER, {"dispatch_trip": self.trip.name})
        frappe.delete_doc("Dispatch Trip", self.trip.name, force=True, ignore_permissions=True)

    def _originals(self):
        return frappe.get_all(
            LEDGER,
            filters={"dispatch_trip": self.trip.name, "reversal_of": ["is", "not set"]},
            fields=["name", "employee", "outcome", "is_cancelled"],
        )

    def test_posts_one_row_per_terminal_outcome(self):
        posted = post_trip_boarding(self.trip.name)
        self.assertEqual(posted, 2, "Only the two terminal-outcome workers post.")

        rows = {r.employee: r for r in self._originals()}
        self.assertEqual(set(rows), {self.boarded_emp, self.absent_emp})
        self.assertEqual(rows[self.boarded_emp].outcome, "Boarded")
        self.assertEqual(rows[self.absent_emp].outcome, "Absent")
        self.assertNotIn(self.pending_emp, rows)

    def test_posted_row_is_immutable(self):
        post_trip_boarding(self.trip.name)
        name = self._originals()[0].name
        doc = frappe.get_doc(LEDGER, name)
        doc.outcome = "Tampered"
        with self.assertRaises(frappe.PermissionError):
            doc.save(ignore_permissions=True)

    def test_posting_is_idempotent(self):
        first = post_trip_boarding(self.trip.name)
        second = post_trip_boarding(self.trip.name)
        self.assertEqual(first, 2, "First pass posts both terminal outcomes.")
        self.assertEqual(second, 0, "Second pass must NOT duplicate.")
        self.assertEqual(len(self._originals()), 2)

    def test_reverse_not_delete_and_idempotent(self):
        post_trip_boarding(self.trip.name)
        originals = self._originals()
        self.assertEqual(len(originals), 2)

        reversed_count = reverse_trip_boarding(self.trip.name)
        self.assertEqual(reversed_count, 2, "Each original posts one reversal.")

        still = {r.name: r for r in self._originals()}
        self.assertEqual(len(still), 2, "Originals are preserved, never deleted.")
        for r in still.values():
            self.assertEqual(r.is_cancelled, 1, "Each original is flagged cancelled.")

        for orig in originals:
            rev = frappe.get_all(
                LEDGER,
                filters={"reversal_of": orig.name},
                fields=["employee", "outcome", "is_cancelled"],
            )
            self.assertEqual(len(rev), 1)
            self.assertEqual(rev[0].employee, orig.employee)
            self.assertEqual(rev[0].is_cancelled, 1)

        again = reverse_trip_boarding(self.trip.name)
        self.assertEqual(again, 0, "A second reversal pass must not double-post.")
