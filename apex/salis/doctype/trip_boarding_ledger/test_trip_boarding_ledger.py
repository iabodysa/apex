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

``test_ignore`` prunes the HR/master auto-dependency walk.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.salis.boarding_engine import post_trip_boarding, reverse_trip_boarding

LEDGER = "Trip Boarding Ledger"

test_ignore = [
    "Employee",
    "Company",
    "Project",
    "Salis Vehicle",
    "Salis Driver",
    "User",
    "Role",
    "Transport Request",
    "Building",
]


def _h(n=12):
    return frappe.generate_hash(length=n).upper()


class TestTripBoardingLedger(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self._cleanup = []

        self.boarded_emp = self._employee()
        self.absent_emp = self._employee()
        self.pending_emp = self._employee()

        self.trip = frappe.get_doc(
            {
                "doctype": "Dispatch Trip",
                "naming_series": "DT-.######",
                "trip_date": "2026-06-20",
                "status": "Planned",
            }
        )
        # [#qdacab]
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
        self._cleanup.append(("Dispatch Trip", self.trip.name))

    def tearDown(self):
        frappe.set_user("Administrator")
        for row in frappe.get_all(
            LEDGER, filters={"dispatch_trip": self.trip.name}, pluck="name"
        ):
            frappe.db.delete(LEDGER, {"reversal_of": row})
        frappe.db.delete(LEDGER, {"dispatch_trip": self.trip.name})
        for dt, name in reversed(self._cleanup):
            frappe.delete_doc(dt, name, force=True, ignore_permissions=True)

    def _employee(self):
        emp = frappe.get_doc(
            {"doctype": "Employee", "first_name": "TBL-" + _h(), "naming_series": "HR-EMP-"}
        )
        emp.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        self._cleanup.append(("Employee", emp.name))
        return emp.name

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
        # [#gn11p0]
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

        # [#9byhd7]
        still = {r.name: r for r in self._originals()}
        self.assertEqual(len(still), 2, "Originals are preserved, never deleted.")
        for r in still.values():
            self.assertEqual(r.is_cancelled, 1, "Each original is flagged cancelled.")

        # [#ixhnhn]
        for orig in originals:
            rev = frappe.get_all(
                LEDGER,
                filters={"reversal_of": orig.name},
                fields=["employee", "outcome", "is_cancelled"],
            )
            self.assertEqual(len(rev), 1)
            self.assertEqual(rev[0].employee, orig.employee)
            self.assertEqual(rev[0].is_cancelled, 1)

        # [#hdkao5]
        again = reverse_trip_boarding(self.trip.name)
        self.assertEqual(again, 0, "A second reversal pass must not double-post.")
