# Copyright (c) 2026, AFMCO and contributors
"""Preliminary transport assignment layer — many-requests -> one-trip.

Covers the supervisor assignment model the desk child table on Dispatch Trip and
``assign_requests_to_trip`` drive:

  * Assigning 2 requests onto a trip makes the trip's expected manifest (and the
    seeded boarding state) the de-duplicated UNION of both requests' workers.
  * The capacity guard throws when the assigned requests' worker total exceeds a
    known vehicle seat_capacity, and is silent when capacity is unknown (0).
  * Assigning flips each request's is_assigned flag + assigned_to_trip back-link
    (best-effort; status stays workflow-owned).

The boarding-state seeding is exercised through boarding_flow.ensure_trip_boarding_state
(the trip-start path), reusing the union resolver the QR scan + worker poll share.
``test_ignore`` prunes the HR/master auto-dependency walk.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.salis.api import boarding_flow
from apex.salis.doctype.dispatch_trip.dispatch_trip import assign_requests_to_trip

test_ignore = [
    "Employee",
    "Company",
    "Project",
    "Salis Vehicle",
    "Salis Driver",
    "User",
    "Role",
    "Transport Request",
]


def _h(n=12):
    return frappe.generate_hash(length=n).upper()


class TestDispatchTripAssignment(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self._cleanup = []

        # Three distinct workers; request A carries w1+w2, request B carries w2+w3
        # (w2 overlaps so the union is 3, not 4).
        self.w1 = self._employee()
        self.w2 = self._employee()
        self.w3 = self._employee()

        self.req_a = self._request([self.w1, self.w2])
        self.req_b = self._request([self.w2, self.w3])

        self.vehicle = frappe.get_doc(
            {
                "doctype": "Salis Vehicle",
                "naming_series": "VEH-.######",
                "plate_number": "ASG " + _h(12),
                "status": "Active",
                "seat_capacity": 0,
            }
        )
        self.vehicle.flags.ignore_validate = True
        self.vehicle.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        self._cleanup.append(("Salis Vehicle", self.vehicle.name))

        self.trip = frappe.get_doc(
            {
                "doctype": "Dispatch Trip",
                "naming_series": "DT-.######",
                "vehicle": self.vehicle.name,
                "trip_date": "2026-06-20",
                "status": "Planned",
            }
        )
        self.trip.flags.ignore_validate = True
        self.trip.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        self._cleanup.append(("Dispatch Trip", self.trip.name))

    def tearDown(self):
        frappe.set_user("Administrator")
        for dt, name in reversed(self._cleanup):
            frappe.delete_doc(dt, name, force=True, ignore_permissions=True)

    # builders

    def _employee(self):
        emp = frappe.get_doc(
            {"doctype": "Employee", "first_name": "ASG-" + _h(), "naming_series": "HR-EMP-"}
        )
        emp.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        self._cleanup.append(("Employee", emp.name))
        return emp.name

    def _request(self, workers):
        req = frappe.get_doc({"doctype": "Transport Request", "worker_count": len(workers)})
        for w in workers:
            req.append("workers", {"employee": w})
        req.flags.ignore_validate = True
        req.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        # worker_count is server-derived in validate(); set it directly since this
        # synthetic insert skips validate.
        frappe.db.set_value("Transport Request", req.name, "worker_count", len(workers), update_modified=False)
        self._cleanup.append(("Transport Request", req.name))
        return req.name

    # union manifest + boarding state

    def test_assign_two_requests_unions_the_manifest(self):
        assign_requests_to_trip(self.trip.name, [self.req_a, self.req_b])

        union = set(boarding_flow._manifest_employees(self.trip.name))
        self.assertEqual(
            union,
            {self.w1, self.w2, self.w3},
            "the trip manifest is the de-duplicated union of both requests' workers",
        )

        added = boarding_flow.ensure_trip_boarding_state(self.trip.name)
        self.assertEqual(added, 3, "boarding state seeds one row per union worker (w2 not doubled)")
        self.trip.reload()
        seeded = {r.employee for r in self.trip.boarding_state}
        self.assertEqual(seeded, {self.w1, self.w2, self.w3})

    # assignment flag back-link

    def test_assign_flags_each_request(self):
        assign_requests_to_trip(self.trip.name, [self.req_a, self.req_b])
        for req in (self.req_a, self.req_b):
            row = frappe.db.get_value(
                "Transport Request", req, ["is_assigned", "assigned_to_trip"], as_dict=True
            )
            self.assertTrue(row.is_assigned, f"{req} is flagged assigned")
            self.assertEqual(row.assigned_to_trip, self.trip.name)

    # capacity guard

    def test_capacity_guard_throws_on_exceed(self):
        # union of 3 workers; cap the vehicle at 2 -> exceed.
        frappe.db.set_value("Salis Vehicle", self.vehicle.name, "seat_capacity", 2)
        with self.assertRaises(frappe.ValidationError):
            assign_requests_to_trip(self.trip.name, [self.req_a, self.req_b])

    def test_capacity_guard_silent_when_capacity_unknown(self):
        # seat_capacity 0 (unknown) -> guard skipped even though 3 > 0 workers.
        result = assign_requests_to_trip(self.trip.name, [self.req_a, self.req_b])
        self.assertEqual(set(result), {self.req_a, self.req_b})

    def test_capacity_guard_allows_within_capacity(self):
        frappe.db.set_value("Salis Vehicle", self.vehicle.name, "seat_capacity", 5)
        result = assign_requests_to_trip(self.trip.name, [self.req_a, self.req_b])
        self.assertEqual(set(result), {self.req_a, self.req_b})

    # idempotent append

    def test_assign_is_idempotent(self):
        assign_requests_to_trip(self.trip.name, [self.req_a])
        result = assign_requests_to_trip(self.trip.name, [self.req_a, self.req_b])
        self.assertEqual(result.count(self.req_a), 1, "a re-assigned request is not duplicated")
        self.assertEqual(set(result), {self.req_a, self.req_b})
