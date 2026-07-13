# Copyright (c) 2026, AFMCO and contributors
"""Pinning tests for the batched _worker_today_dispatch_trip resolver (P-210 N+1).

The resolver used to make O(trips x requests) DB round-trips on the worker
boarding poll (a hot, guest-facing path): one Route Plan lookup per trip, one
assigned-request read per trip, and one Transport Request Worker + Transport
Request read per candidate. P-210 collapses those into three bulk reads joined in
memory. Behaviour is byte-identical, so these tests pin the resolver OUTPUT
against a real multi-trip x multi-request fixture:

  * the earliest-departing trip the worker is on wins, and the returned
    (dispatch_trip, transport_request, pickup_point, accommodation_building)
    tuple is exact;
  * a worker reached only through the supervisor's assigned-request union (not the
    trip's direct request) still resolves to that trip + assigned request;
  * a client-supplied transport_request narrows the own-set to that request's trip.

test_ignore prunes the HR/master auto-dependency walk; fixtures insert with
ignore_validate/links/mandatory so the resolver logic is exercised without a full
fleet graph.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today

from apex.salis.api import masar

test_ignore = [
    "Employee",
    "Building",
    "Route Plan",
    "Salis Driver",
    "Transport Request",
]


def _h(n=10):
    return frappe.generate_hash(length=n).upper()


class TestMasarDispatchBatch(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self._cleanup = []

        self.emp = frappe.get_doc(
            {"doctype": "Employee", "first_name": "MDB-" + _h(), "naming_series": "HR-EMP-"}
        )
        self.emp.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        self._track("Employee", self.emp.name)

        self.other = frappe.get_doc(
            {"doctype": "Employee", "first_name": "MDB2-" + _h(), "naming_series": "HR-EMP-"}
        )
        self.other.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        self._track("Employee", self.other.name)

        self.building = frappe.get_doc(
            {"doctype": "Building", "building_name": "MDB Bldg " + _h()}
        ).insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        self._track("Building", self.building.name)

    def tearDown(self):
        frappe.set_user("Administrator")
        for dt, name in reversed(self._cleanup):
            frappe.delete_doc(dt, name, force=True, ignore_permissions=True)

    def _track(self, dt, name):
        self._cleanup.append((dt, name))

    def _request(self, worker=None, pickup=None, building=None):
        req = frappe.get_doc(
            {
                "doctype": "Transport Request",
                "request_date": today(),
                "accommodation_building": building,
            }
        )
        if worker:
            req.append("workers", {"employee": worker, "pickup_point": pickup})
        req.flags.ignore_validate = True
        req.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        self._track("Transport Request", req.name)
        return req

    def _trip(self, transport_request=None, depart_time="06:00:00", assigned=None):
        trip = frappe.get_doc(
            {
                "doctype": "Dispatch Trip",
                "naming_series": "DT-.######",
                "transport_request": transport_request,
                "trip_date": today(),
                "depart_time": depart_time,
                "status": "Planned",
            }
        )
        for req_name in assigned or []:
            trip.append("assigned_requests", {"transport_request": req_name})
        trip.flags.ignore_validate = True
        trip.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        self._track("Dispatch Trip", trip.name)
        return trip

    def test_earliest_trip_on_manifest_wins_with_exact_tuple(self):
        # [#gywrk2]
        req_early = self._request(self.emp.name, "PICK-EARLY", self.building.name)
        req_late = self._request(self.emp.name, "PICK-LATE", self.building.name)
        trip_early = self._trip(req_early.name, depart_time="06:00:00")
        self._trip(req_late.name, depart_time="08:00:00")

        resolved = masar._worker_today_dispatch_trip(self.emp.name)
        self.assertEqual(
            resolved,
            (trip_early.name, req_early.name, "PICK-EARLY", self.building.name),
        )

    def test_assigned_request_union_resolves_when_not_on_direct_request(self):
        # [#3dqxyi]
        req_direct = self._request(self.other.name, "OTHER-PICK", self.building.name)
        req_assigned = self._request(self.emp.name, "ASG-PICK", self.building.name)
        trip = self._trip(req_direct.name, assigned=[req_assigned.name])

        resolved = masar._worker_today_dispatch_trip(self.emp.name)
        self.assertEqual(
            resolved,
            (trip.name, req_assigned.name, "ASG-PICK", self.building.name),
        )

    def test_transport_request_filter_narrows_to_that_requests_trip(self):
        # [#dficmb]
        req_early = self._request(self.emp.name, "PICK-EARLY", self.building.name)
        req_late = self._request(self.emp.name, "PICK-LATE", self.building.name)
        self._trip(req_early.name, depart_time="06:00:00")
        trip_late = self._trip(req_late.name, depart_time="08:00:00")

        resolved = masar._worker_today_dispatch_trip(self.emp.name, req_late.name)
        self.assertEqual(
            resolved,
            (trip_late.name, req_late.name, "PICK-LATE", self.building.name),
        )

    def test_worker_with_no_trip_today_is_none(self):
        # [#dk1k98]
        self.assertIsNone(masar._worker_today_dispatch_trip(self.emp.name))
