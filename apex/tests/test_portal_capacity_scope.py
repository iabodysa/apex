# Copyright (c) 2026, afmcoltd
"""A portal capacity may WRITE the row the token bound it to, and may still read nothing.

The two capacity identities stand in for every driver and every worker at once, so neither
can hold a Project or Building User Permission — there is no single tenant to name. Before
this, the tenant layer read that absence as "no projects" and refused every portal write
behind ``as_capacity``: the QR scan, the self-confirm, the fuel request, the trip rating,
the worker's own Transport Request and Resident Request.

The answer is the identity exemption in ``permission_scope``: the capacity's write defers
to the capacity role's DocPerm, which is the wall it was created to carry. The other half
of the answer is what these cases pin just as hard — a capacity gained no read. The list
fragment is "1=0" on both tenant axes, and a single document still refuses ``read``.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.apex_core.utils import permission_scope
from apex.apex_core.utils.portal_identity import DRIVER, WORKER, as_capacity
from apex.habitat.permissions import building_scope_query
from apex.salis.api import boarding_flow
from apex.salis.permissions import SALIS_SCOPE, project_scope_query
from apex.tests.factories import (
    WorkerTripMixin,
    make_masar_building,
    make_project,
    make_test_driver,
    make_vehicle,
    make_worker_employee,
    purge_doc,
)

DRIVER_CAPACITY = "driver@apex.internal"
WORKER_CAPACITY = "worker@apex.internal"


class TestPortalCapacityScope(WorkerTripMixin, FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.project = make_project("Apex Capacity Scope")
        cls.building = make_masar_building("Apex Capacity Scope Building")
        cls.driver = make_test_driver()
        cls.worker = make_worker_employee("Capacity Scope Worker")
        cls.vehicle = make_vehicle("CAP SCOPE 1", project=cls.project)

    def setUp(self):
        frappe.set_user("Administrator")
        self.tr, self.rp, self.trip = self._worker_trip(
            self.driver,
            self.project,
            self.building,
            [self.worker],
            "Capacity Scope Route",
        )

    def _rating(self):
        return frappe.get_doc(
            {
                "doctype": "Transport Trip Rating",
                "employee": self.worker,
                "dispatch_trip": self.trip.name,
                "rating": 5,
            }
        )

    def _fuel_request(self):
        return frappe.get_doc(
            {
                "doctype": "Fuel Request",
                "request_type": "Standard",
                "vehicle": self.vehicle,
                "driver": self.driver,
                "requested_litres": 10,
                "request_date": frappe.utils.today(),
                "status": "Pending",
            }
        )

    def test_the_driver_capacity_seeds_the_trip_boarding_state(self):
        """boarding_flow.ensure_trip_boarding_state — the trip-start path.

        The rows are cleared first because ``sync_passengers`` already rebuilt them on
        the factory's own save, which would leave this helper with nothing to add and
        no save to grade.
        """
        frappe.db.delete("Trip Boarding State", {"parent": self.trip.name})
        self.trip.reload()
        self.assertEqual(boarding_flow.ensure_trip_boarding_state(self.trip.name), 1)
        self.trip.reload()
        self.assertEqual([r.employee for r in self.trip.boarding_state], [self.worker])

    def test_the_driver_capacity_marks_a_rider_boarded(self):
        """boarding_flow.mark_boarded under the Driver capacity — every QR scan."""
        boarding_flow.mark_boarded(self.trip.name, self.worker, audience=DRIVER)
        self.trip.reload()
        self.assertEqual(self.trip.boarding_state[0].status, "Boarded")

    def test_the_worker_capacity_marks_a_rider_boarded(self):
        """The same write under the Worker capacity — the rider's own self-confirm."""
        boarding_flow.mark_boarded(
            self.trip.name, self.worker, source="Worker", audience=WORKER
        )
        self.trip.reload()
        self.assertEqual(self.trip.boarding_state[0].status, "Boarded")

    def test_the_driver_capacity_creates_a_fuel_request(self):
        """fleet_employee.request_fuel — the /fleet fuel request."""
        doc = self._fuel_request()
        self.assertTrue(
            frappe.has_permission("Fuel Request", "create", doc=doc, user=DRIVER_CAPACITY)
        )
        with as_capacity(DRIVER):
            doc.insert()
        self.addCleanup(purge_doc, "Fuel Request", doc.name)
        self.assertTrue(frappe.db.exists("Fuel Request", doc.name))

    def test_the_worker_capacity_creates_a_trip_rating(self):
        """masar.submit_trip_rating — and the DocType is project-scoped now."""
        doc = self._rating()
        self.assertTrue(
            frappe.has_permission(
                "Transport Trip Rating", "create", doc=doc, user=WORKER_CAPACITY
            )
        )
        with as_capacity(WORKER):
            doc.insert()
        self.addCleanup(purge_doc, "Transport Trip Rating", doc.name)
        self.assertTrue(frappe.db.exists("Transport Trip Rating", doc.name))

    def test_the_worker_capacity_creates_a_resident_request(self):
        """masar.submit_worker_request — the Habitat half of the same failure."""
        doc = frappe.get_doc(
            {
                "doctype": "Resident Request",
                "source_channel": "QR Web Form",
                "requester_type": "Worker",
                "employee": self.worker,
                "building": self.building,
                "request_category": "Other",
                "description": "Capacity scope probe",
                "status": "New",
            }
        )
        self.assertTrue(
            frappe.has_permission("Resident Request", "create", doc=doc, user=WORKER_CAPACITY)
        )

    def test_a_capacity_write_still_stops_at_the_permlevel_wall(self):
        """The DocPerm the exemption defers to is already narrowed to the rider's own row.

        Every Dispatch Trip field but ``boarding_state`` sits at permlevel 1 and neither
        capacity role holds a level-1 grant, so the framework RESETS the value rather
        than refusing the save — the assertion is on what is stored, not on an exception.
        """
        frappe.db.set_value("Dispatch Trip", self.trip.name, "completion_notes", "dispatch wrote this")
        trip = frappe.get_doc("Dispatch Trip", self.trip.name)
        trip.completion_notes = "the capacity rewrote this"
        with as_capacity(DRIVER):
            trip.save()
        self.assertEqual(
            frappe.db.get_value("Dispatch Trip", self.trip.name, "completion_notes"),
            "dispatch wrote this",
        )

    def test_a_capacity_gains_no_document_read(self):
        """The exemption is for the write only, so the deferral cannot widen into a read."""
        for user in (DRIVER_CAPACITY, WORKER_CAPACITY):
            with self.subTest(user=user):
                self.assertFalse(
                    frappe.has_permission(
                        "Dispatch Trip", "read", doc=self.trip, user=user
                    )
                )
                self.assertFalse(
                    frappe.has_permission(
                        "Transport Trip Rating", "read", doc=self._rating(), user=user
                    )
                )

    def test_a_capacity_lists_nothing_on_either_tenant_axis(self):
        """An own-row clause would resolve to the capacity's OWN name, i.e. every project."""
        for user in (DRIVER_CAPACITY, WORKER_CAPACITY):
            for doctype in sorted(SALIS_SCOPE):
                with self.subTest(user=user, doctype=doctype):
                    self.assertEqual(project_scope_query(user=user, doctype=doctype), "1=0")
            with self.subTest(user=user, doctype="Resident Request"):
                self.assertEqual(
                    building_scope_query(user=user, doctype="Resident Request"), "1=0"
                )

    def test_the_exemption_is_keyed_on_the_identity_not_the_role(self):
        """Real people hold the Driver role, so keying on the role would catch them too.

        Their fragment must stay the own-row clause it is: "1=0" here would mean the
        exemption had reached a person, and a person's list must not close either.
        """
        holders = frappe.get_all("Has Role", filters={"role": "Driver"}, pluck="parent")
        people = [
            u
            for u in holders
            if "@" in u
            and not permission_scope.is_portal_capacity(u)
            and frappe.db.exists("User", u)
        ]
        self.assertTrue(people, "no human Driver-role holder on this site to test against")
        for user in people:
            with self.subTest(user=user):
                self.assertNotEqual(project_scope_query(user=user, doctype="Fuel Request"), "1=0")
