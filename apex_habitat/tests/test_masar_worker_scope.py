"""Masar worker-scope tests (P-045): a worker is NOT the driver.

The driver navigates every housing pickup on a multi-building shuttle plus the
drop-off; a WORKER only cares about two points — where the shuttle collects HIM
(the stop at his own accommodation building) and where it is going (the route's
final drop-off). ``masar.get_worker_transport`` must therefore scope each trip's
multi-stop route down to ``my_pickup`` + ``destination`` for the token's own
worker, never leaking other buildings' housing pickups to him.

These tests build a single Workers-line route with THREE housing pickups
(buildings A/B/C) followed by one drop-off, give a token-scoped worker an active
Accommodation Assignment in building B, and assert the worker-scoped pair:

  * ``my_pickup``    — the housing pickup whose accommodation_building == the
    worker's active assignment building (B, not A or C), with a fallback to the
    first housing pickup when the worker's building does not appear on the route;
  * ``destination``  — the route's final drop-off stop (the point after every
    housing pickup), never one of the housing pickups.

The boarding pass (``get_worker_boarding_pass``) is asserted to carry the same
pair as ``pickup_label`` (the worker's building) + ``destination_label`` (the
drop-off) rather than the generic per-request pickup_point for both.
"""


import frappe
from frappe.tests.utils import FrappeTestCase

from apex_habitat.salis.api import masar
from apex_habitat.tests.test_driver_portal import _ensure_test_driver
from apex_habitat.tests.factories import make_bed, make_room
from apex_habitat.tests.test_masar_worker_movement import (
    _WorkerTripMixin,
    _building,
    _employee,
    _project,
)


def _make_token(employee, enabled=1):
    """Issue a Masar Worker Token for ``employee`` (token auto-minted)."""
    return (
        frappe.get_doc(
            {
                "doctype": "Masar Worker Token",
                "party_type": "Employee",
                "party": employee,
                "employee": employee,
                "enabled": enabled,
            }
        )
        .insert(ignore_permissions=True)
        .token
    )


def _assign(employee, building, project):
    """A submitted, not-checked-out Accommodation Assignment for the worker, with a
    real room+bed in ``building`` (room/bed are mandatory). Only the building
    matters for the worker-pickup scoping under test, but the full chain keeps the
    assignment controller happy. A default cost center is stamped on the building
    so submit's deduction/cost-center path passes."""
    room = make_room(building, room_number=f"{building}-SCOPE-R", bed_capacity=4)
    bed = make_bed(room.name, bed_code=f"{building}-SCOPE-B")
    company = frappe.db.get_value("Accommodation Building", building, "company") or _company_default()
    cost_center = frappe.db.get_value(
        "Cost Center", {"company": company, "is_group": 0}, "name"
    )
    doc = frappe.get_doc(
        {
            "doctype": "Accommodation Assignment",
            "employee": employee,
            "building": building,
            "room": room.name,
            "bed": bed.name,
            "project": project,
            "cost_center": cost_center,
            "check_in_date": frappe.utils.today(),
            "stay_type": "Permanent",
        }
    )
    doc.insert(ignore_permissions=True)
    doc.submit()
    return doc.name


def _company_default():
    return (
        frappe.defaults.get_global_default("company")
        or frappe.get_all("Company", limit=1)[0].name
    )


class TestMasarWorkerScope(_WorkerTripMixin, FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        frappe.db.set_single_value("Salis Settings", "enable_driver_portal", 1)
        cls.project = _project("Masar Scope Project")
        cls.bldg_a = _building("Masar Scope Residence A")
        cls.bldg_b = _building("Masar Scope Residence B")
        cls.bldg_c = _building("Masar Scope Residence C")
        cls.driver = _ensure_test_driver()
        # Worker lives in building B — the MIDDLE pickup, so a pass/fail can't be a
        # coincidence of "first stop" or "last stop".
        cls.worker = _employee("Masar Scope Worker B")
        cls.token = _make_token(cls.worker)

    def setUp(self):
        frappe.set_user("Administrator")

    def tearDown(self):
        frappe.set_user("Administrator")

    def _multi_building_trip(self, route_name):
        """A Workers-line trip whose route has THREE housing pickups (A/B/C) plus
        a final drop-off, with the token worker on the manifest. Returns
        ``(tr, rp, dt)`` and registers cleanup via the mixin."""
        tr = frappe.get_doc(
            {
                "doctype": "Transport Request",
                "service_line": "Site Transport",
                "request_type": "Accommodation to Project Shuttle",
                "project": self.project,
                "accommodation_building": self.bldg_b,
                "from_location": "Building Gate",
                "to_location": "Project Site",
                "source_channel": "Desk",
                "status": "New",
                "pickup_datetime": frappe.utils.add_to_date(
                    frappe.utils.today(), hours=30
                ),
                "workers": [{"employee": self.worker, "pickup_point": "Building Gate"}],
            }
        ).insert(ignore_permissions=True)
        tr.reload()

        rp = frappe.get_doc(
            {
                "doctype": "Route Plan",
                "route_name": route_name,
                "transport_request": tr.name,
                "project": self.project,
                "driver": self.driver,
                "stops": [
                    {
                        "sequence": 1,
                        "stop_name": "Housing Pickup 1",
                        "accommodation_building": self.bldg_a,
                        "location": "Building Gate",
                        "passengers": 0,
                    },
                    {
                        "sequence": 2,
                        "stop_name": "Housing Pickup 2",
                        "accommodation_building": self.bldg_b,
                        "location": "Building Gate",
                        "passengers": 1,
                    },
                    {
                        "sequence": 3,
                        "stop_name": "Housing Pickup 3",
                        "accommodation_building": self.bldg_c,
                        "location": "Building Gate",
                        "passengers": 0,
                    },
                    {
                        "sequence": 4,
                        "stop_name": "Project Drop-off",
                        "location": "Project Site",
                        "passengers": 0,
                    },
                ],
            }
        ).insert(ignore_permissions=True)

        # Stamp the route plan back onto the request (the live flow does this when
        # the Route Plan is submitted; we set it directly to avoid driving the full
        # scheduling workflow, which is out of scope for this read-path test).
        frappe.db.set_value("Transport Request", tr.name, "route_plan", rp.name)

        dt = frappe.get_doc(
            {
                "doctype": "Dispatch Trip",
                "route_plan": rp.name,
                "transport_request": tr.name,
                "driver": self.driver,
                "trip_date": frappe.utils.today(),
                "depart_time": "06:30:00",
                "status": "Planned",
            }
        ).insert(ignore_permissions=True)
        self.addCleanup(lambda: self._purge(dt.name, rp.name, tr.name))
        return tr, rp, dt

    def _trip_for(self, request_name):
        """The worker's transport trip for ``request_name`` (the test owns it, so
        match by id rather than assuming it is the only/first upcoming trip — a
        non-fresh DB may carry other demo trips for this employee)."""
        payload = masar.get_worker_transport(token=self.token)
        for trip in payload["upcoming"] + payload["past"]:
            if trip["transport_request"] == request_name:
                return trip
        return None

    def test_worker_sees_only_own_pickup_and_destination(self):
        """The worker (in building B) gets my_pickup = B's housing pickup and
        destination = the drop-off — NOT all three housing pickups."""
        self._assign_name = _assign(self.worker, self.bldg_b, self.project)
        self.addCleanup(self._purge_assignment)
        tr, _rp, _dt = self._multi_building_trip("Scope Route A")

        trip = self._trip_for(tr.name)
        self.assertIsNotNone(trip, "fixture sanity: the worker's trip is returned")

        # The worker-scoped pickup is HIS building's housing pickup (B), the middle
        # stop — proving the match is by accommodation_building, not stop position.
        self.assertIsNotNone(trip["my_pickup"])
        self.assertEqual(trip["my_pickup"]["accommodation_building"], self.bldg_b)
        self.assertEqual(trip["my_pickup"]["stop_name"], "Housing Pickup 2")

        # The destination is the final drop-off, NOT a housing pickup.
        self.assertIsNotNone(trip["destination"])
        self.assertEqual(trip["destination"]["stop_name"], "Project Drop-off")
        self.assertEqual(trip["destination"]["location"], "Project Site")
        self.assertIsNone(trip["destination"]["accommodation_building"])

        # Anti-leak: the worker's two-point view is NOT the other buildings'
        # pickups. (The full `stops` list is still carried for any driver-facing
        # caller, but my_pickup/destination are the worker's scoped pair.)
        self.assertNotEqual(
            trip["my_pickup"]["accommodation_building"], self.bldg_a
        )
        self.assertNotEqual(
            trip["my_pickup"]["accommodation_building"], self.bldg_c
        )

    def test_unresolved_building_falls_back_to_first_housing_pickup(self):
        """A worker with NO active assignment (building unresolved) still gets a
        sane pickup — the first housing pickup — plus the destination, never a
        blank or the whole route."""
        # No _assign() here: the worker has no active assignment.
        tr, _rp, _dt = self._multi_building_trip("Scope Route B")

        trip = self._trip_for(tr.name)
        self.assertIsNotNone(trip, "fixture sanity: the worker's trip is returned")
        self.assertIsNotNone(trip["my_pickup"])
        # Fallback = the first stop carrying an accommodation_building (A).
        self.assertEqual(trip["my_pickup"]["accommodation_building"], self.bldg_a)
        self.assertEqual(trip["destination"]["stop_name"], "Project Drop-off")

    def test_boarding_pass_destination_is_dropoff_and_pickup_is_own_building(self):
        """The pass carries the route's drop-off as destination_label and the
        worker's own building as pickup_label — not the generic pickup_point for
        both."""
        self._assign_name = _assign(self.worker, self.bldg_b, self.project)
        self.addCleanup(self._purge_assignment)
        self._multi_building_trip("Scope Route C")

        res = masar.get_worker_boarding_pass(token=self.token)
        self.assertIsNotNone(res["pass"], "fixture sanity: the worker has a boardable trip today")
        pass_ = res["pass"]

        # Destination = the drop-off location, NOT "Building Gate".
        self.assertEqual(pass_["destination_label"], "Project Site")
        # Pickup = the worker's own building (B), NOT the generic "Building Gate".
        self.assertEqual(pass_["pickup_label"], "Masar Scope Residence B")

    def _purge_assignment(self):
        frappe.set_user("Administrator")
        name = getattr(self, "_assign_name", None)
        if name and frappe.db.exists("Accommodation Assignment", name):
            doc = frappe.get_doc("Accommodation Assignment", name)
            if doc.docstatus == 1:
                try:
                    doc.cancel()
                except Exception:
                    pass
            frappe.delete_doc(
                "Accommodation Assignment", name, ignore_permissions=True, force=True
            )
