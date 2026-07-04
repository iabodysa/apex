# Copyright (c) 2026, AFMCO and contributors
"""P-063 — Masar live ride ETA from a driver-GPS position (end-to-end).

The worker's Home ``next_ride`` card must show a SERVER-computed ETA derived from
the driver's live GPS position. This test proves the full path:

  driver portal pushes a GPS fix  ->  ``driver_portal.push_driver_position``
  stores it on the Dispatch Trip   ->  ``masar.get_worker_home`` computes the ETA
  (haversine(driver -> worker's pickup building) / assumed fleet speed) and
  attaches it to ``next_ride.eta_minutes``.

Determinism (non-coincidental value, asserted exactly, not just truthy):

  * pickup building at (24.700000, 46.700000)
  * driver GPS fix   at (24.700000, 46.800000)  -> same latitude, dlng 0.1 deg
  * haversine distance = 10.10216... km
  * assumed fleet speed pinned to 40 km/h -> (10.10216/40)*60 = 15.153... min
  * rounded to whole minutes -> 15

If the ETA computation is removed (or the position/coords are dropped), the
payload carries no ``eta_minutes`` (or None) and ``test_next_ride_eta_is_computed``
fails on the exact-value assertion — the test is non-vacuous.
"""


import frappe
from frappe.tests.utils import FrappeTestCase

from apex_habitat.salis.api import driver_portal, masar
from apex_habitat.tests.test_masar_worker_movement import (
    _company,
    _ensure_driver_chain,
    _employee,
    _project,
    _site,
)

# The deterministic geometry under test.
_PICKUP_LAT = 24.700000
_PICKUP_LNG = 46.700000
_DRIVER_LAT = 24.700000
_DRIVER_LNG = 46.800000
_ASSUMED_SPEED_KMPH = 40.0
_EXPECTED_ETA_MIN = 15  # (10.10216 km / 40 km/h) * 60 = 15.153 -> round -> 15


def _make_token(employee):
    return (
        frappe.get_doc(
            {
                "doctype": "Masar Worker Token",
                "party_type": "Employee",
                "party": employee,
                "employee": employee,
                "enabled": 1,
            }
        )
        .insert(ignore_permissions=True)
        .token
    )


def _building_with_coords(name, lat, lng):
    """Get-or-create a building carrying pickup coordinates (idempotent on re-run)."""
    existing = frappe.db.get_value("Accommodation Building", {"building_name": name}, "name")
    if existing:
        frappe.db.set_value(
            "Accommodation Building", existing, {"pickup_lat": lat, "pickup_lng": lng}
        )
        return existing
    return (
        frappe.get_doc(
            {
                "doctype": "Accommodation Building",
                "building_name": name,
                "site": _site("Masar GPS Test Site"),
                "total_capacity": 20,
                "pickup_lat": lat,
                "pickup_lng": lng,
            }
        )
        .insert(ignore_permissions=True)
        .name
    )


def _driver_user(driver):
    emp = frappe.db.get_value("Salis Driver", driver, "employee")
    return frappe.db.get_value("Employee", emp, "user_id")


class TestDriverGpsEta(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        frappe.db.set_single_value("Salis Settings", "enable_driver_portal", 1)
        # Pin the speed so the expected ETA is independent of the stored/blank value.
        frappe.db.set_single_value("Salis Settings", "assumed_fleet_speed_kmph", _ASSUMED_SPEED_KMPH)
        cls.project = _project("Masar GPS Project")
        cls.building = _building_with_coords("Masar GPS Residence", _PICKUP_LAT, _PICKUP_LNG)
        cls.driver, cls.driver_email = _ensure_driver_chain(
            "masar-gps-driver@example.com", "GPS Driver"
        )
        # A SECOND driver, to prove the ingestion API is ownership-scoped.
        cls.other_driver, cls.other_email = _ensure_driver_chain(
            "masar-gps-other@example.com", "GPS Other"
        )
        frappe.db.commit()

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        if frappe.db.exists("Project", cls.project):
            frappe.delete_doc("Project", cls.project, ignore_permissions=True, force=True)
        frappe.db.commit()
        super().tearDownClass()

    def setUp(self):
        frappe.set_user("Administrator")
        # A pristine worker PER TEST: the shared test bench accumulates committed
        # Transport Requests, and next_ride is the soonest upcoming ride across ALL
        # of a worker's requests — a reused worker would surface a stale leftover ride
        # instead of this test's dispatched trip. A unique worker owns exactly the one
        # ride each test builds, so next_ride is deterministically that ride.
        self.worker = _employee(f"Masar GPS Worker {frappe.generate_hash(length=6)}")
        self.token = _make_token(self.worker)

    def tearDown(self):
        frappe.set_user("Administrator")

    # ── fixtures ──────────────────────────────────────────────────────────────
    def _assign_worker(self):
        """A submitted Accommodation Assignment putting the worker in the pickup
        building, so ``get_worker_transport`` scopes ``my_pickup`` to it."""
        room = frappe.get_doc(
            {
                "doctype": "Accommodation Room",
                "room_number": f"{self.building}-GPS-R",
                "building": self.building,
                "bed_capacity": 4,
                "status": "Available",
            }
        )
        if not frappe.db.exists("Accommodation Room", room.room_number):
            room.insert(ignore_permissions=True)
        bed_code = f"{self.building}-GPS-B"
        if not frappe.db.exists("Accommodation Bed", bed_code):
            frappe.get_doc(
                {
                    "doctype": "Accommodation Bed",
                    "bed_code": bed_code,
                    "room": f"{self.building}-GPS-R",
                    "status": "Available",
                }
            ).insert(ignore_permissions=True)
        company = frappe.db.get_value("Accommodation Building", self.building, "company") or _company()
        cost_center = frappe.db.get_value("Cost Center", {"company": company, "is_group": 0}, "name")
        doc = frappe.get_doc(
            {
                "doctype": "Accommodation Assignment",
                "employee": self.worker,
                "building": self.building,
                "room": f"{self.building}-GPS-R",
                "bed": bed_code,
                "project": self.project,
                "cost_center": cost_center,
                "check_in_date": frappe.utils.today(),
                "stay_type": "Permanent",
            }
        )
        doc.insert(ignore_permissions=True)
        doc.submit()
        self.addCleanup(lambda: self._purge_assignment(doc.name))
        return doc.name

    def _dispatched_trip(self, driver=None):
        """A dispatched Workers-line trip for the worker on ``driver``'s manifest,
        as the soonest upcoming ride. Returns the Dispatch Trip name."""
        driver = driver or self.driver
        tr = frappe.get_doc(
            {
                "doctype": "Transport Request",
                "service_line": "Site Transport",
                "request_type": "Accommodation to Project Shuttle",
                "project": self.project,
                "accommodation_building": self.building,
                "from_location": "Building Gate",
                "to_location": "Project Site",
                "source_channel": "Desk",
                "status": "New",
                # Soonest upcoming: a couple of hours out (>= now, so it is next_ride).
                "pickup_datetime": frappe.utils.add_to_date(frappe.utils.now_datetime(), hours=2),
                "workers": [{"employee": self.worker, "pickup_point": "Building Gate"}],
            }
        ).insert(ignore_permissions=True)
        rp = frappe.get_doc(
            {
                "doctype": "Route Plan",
                "route_name": f"GPS Route {frappe.generate_hash(length=6)}",
                "transport_request": tr.name,
                "project": self.project,
                "driver": driver,
                "stops": [
                    {
                        "sequence": 1,
                        "stop_name": "Housing Pickup",
                        "accommodation_building": self.building,
                        "location": "Building Gate",
                        "passengers": 1,
                    },
                    {
                        "sequence": 2,
                        "stop_name": "Project Drop-off",
                        "location": "Project Site",
                        "passengers": 0,
                    },
                ],
            }
        ).insert(ignore_permissions=True)
        frappe.db.set_value("Transport Request", tr.name, "route_plan", rp.name)
        dt = frappe.get_doc(
            {
                "doctype": "Dispatch Trip",
                "route_plan": rp.name,
                "transport_request": tr.name,
                "driver": driver,
                "trip_date": frappe.utils.today(),
                "depart_time": "06:30:00",
            }
        ).insert(ignore_permissions=True)
        # A new trip must start Planned (controller guard); advance it to Dispatched
        # (docstatus 0 — not submitted) the way the driver is en route when a position
        # streams in. The direct status write bypasses only the workflow UI, never the
        # ingestion/ETA path under test.
        frappe.db.set_value("Dispatch Trip", dt.name, "status", "Dispatched")
        self.addCleanup(lambda: self._purge_trip(dt.name, rp.name, tr.name))
        return dt.name

    # ── the goal: server-computed ETA on next_ride ─────────────────────────────
    def test_next_ride_eta_is_computed(self):
        """Feed a driver GPS fix via the ingestion API, then assert Home's
        next_ride carries the exact server-computed ETA (15 min)."""
        self._assign_worker()
        dt = self._dispatched_trip()

        # The driver pushes their live position through the permission-gated API,
        # impersonating the real driver login (not a raw db write).
        frappe.set_user(self.driver_email)
        result = driver_portal.push_driver_position(
            dispatch_trip=dt, lat=_DRIVER_LAT, lng=_DRIVER_LNG
        )
        self.assertEqual(result["driver_lat"], _DRIVER_LAT)
        self.assertEqual(result["driver_lng"], _DRIVER_LNG)
        self.assertIsNotNone(result["driver_position_updated_at"])
        frappe.set_user("Administrator")

        # The position landed on the trip.
        self.assertEqual(frappe.db.get_value("Dispatch Trip", dt, "driver_lat"), _DRIVER_LAT)

        home = masar.get_worker_home(token=self.token)
        next_ride = home["next_ride"]
        self.assertIsNotNone(next_ride, "fixture sanity: the worker has a next ride")
        self.assertEqual(next_ride["dispatch_trip"], dt)
        # The load-bearing assertion: the EXACT server-computed ETA, deterministic
        # from the known haversine distance and pinned speed.
        self.assertEqual(next_ride["eta_minutes"], _EXPECTED_ETA_MIN)

    def test_eta_is_none_without_a_position(self):
        """Non-vacuity guard: with the SAME fixture but no pushed GPS fix, the ETA
        is None — so the computation, not the fixture, produces the 15 above."""
        self._assign_worker()
        dt = self._dispatched_trip()
        home = masar.get_worker_home(token=self.token)
        self.assertEqual(home["next_ride"]["dispatch_trip"], dt)
        self.assertIsNone(home["next_ride"]["eta_minutes"])

    # ── ingestion API: permission + validation gates ───────────────────────────
    def test_push_rejects_another_drivers_trip(self):
        """A driver may not write a position onto a trip that is not theirs — the
        ownership guard fails closed."""
        self._assign_worker()
        dt = self._dispatched_trip(driver=self.driver)  # belongs to self.driver
        frappe.set_user(self.other_email)  # a DIFFERENT driver
        with self.assertRaises(frappe.DoesNotExistError):
            driver_portal.push_driver_position(dispatch_trip=dt, lat=_DRIVER_LAT, lng=_DRIVER_LNG)
        frappe.set_user("Administrator")
        # Nothing was written — a never-pushed Float field is stored as 0.0 (Frappe
        # defaults an empty Float to 0, not NULL), so the rejected foreign push must
        # leave it falsy.
        self.assertFalse(frappe.db.get_value("Dispatch Trip", dt, "driver_lat"))

    def test_push_rejects_out_of_range_coords(self):
        """Latitude/longitude outside WGS-84 ranges are rejected."""
        self._assign_worker()
        dt = self._dispatched_trip()
        frappe.set_user(self.driver_email)
        with self.assertRaises(frappe.ValidationError):
            driver_portal.push_driver_position(dispatch_trip=dt, lat=200.0, lng=46.7)
        with self.assertRaises(frappe.ValidationError):
            driver_portal.push_driver_position(dispatch_trip=dt, lat="not-a-number", lng=46.7)
        frappe.set_user("Administrator")

    # ── cleanup ────────────────────────────────────────────────────────────────
    def _purge_assignment(self, name):
        frappe.set_user("Administrator")
        if name and frappe.db.exists("Accommodation Assignment", name):
            doc = frappe.get_doc("Accommodation Assignment", name)
            if doc.docstatus == 1:
                try:
                    doc.cancel()
                except Exception:
                    pass
            frappe.delete_doc("Accommodation Assignment", name, ignore_permissions=True, force=True)

    def _purge_trip(self, dt_name, rp_name, tr_name):
        frappe.set_user("Administrator")
        for dtype, name in (
            ("Dispatch Trip", dt_name),
            ("Route Plan", rp_name),
            ("Transport Request", tr_name),
        ):
            if frappe.db.exists(dtype, name):
                doc = frappe.get_doc(dtype, name)
                if doc.docstatus == 1:
                    try:
                        doc.cancel()
                    except Exception:
                        pass
                frappe.delete_doc(dtype, name, ignore_permissions=True, force=True)
