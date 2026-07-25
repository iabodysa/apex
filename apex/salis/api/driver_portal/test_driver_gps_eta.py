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

from apex.salis.api import driver_portal, masar
from apex.tests import factories

# [#hp6kkb]
_PICKUP_LAT = 24.700000
_PICKUP_LNG = 46.700000
_DRIVER_LAT = 24.700000
_DRIVER_LNG = 46.800000
_ASSUMED_SPEED_KMPH = 40.0
_EXPECTED_ETA_MIN = 15  # [#se6l8h]


class TestDriverGpsEta(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        frappe.db.set_single_value("Salis Settings", "enable_driver_portal", 1)
        # [#k9vbl9]
        frappe.db.set_single_value("Salis Settings", "assumed_fleet_speed_kmph", _ASSUMED_SPEED_KMPH)
        cls.project = factories.make_project("Masar GPS Project")
        cls.building = factories.make_building_with_coords(
            "Masar GPS Residence", _PICKUP_LAT, _PICKUP_LNG
        )
        cls.driver, cls.driver_email = factories.make_driver_chain(
            "masar-gps-driver@example.com", "GPS Driver"
        )
        # [#5qt121]
        cls.other_driver, cls.other_email = factories.make_driver_chain(
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
        # [#ioxpy9]
        self.worker = factories.make_worker_employee(
            f"Masar GPS Worker {frappe.generate_hash(length=12)}"
        )
        self.token = factories.make_worker_token(self.worker)

    def tearDown(self):
        frappe.set_user("Administrator")

    # [#88mv24]
    def _assign_worker(self):
        """A submitted Accommodation Assignment putting the worker in the pickup
        building, so ``get_worker_transport`` scopes ``my_pickup`` to it."""
        name = factories.make_assignment(self.worker, self.building, self.project)
        self.addCleanup(lambda: self._purge_assignment(name))
        return name

    def _dispatched_trip(self, driver=None):
        """A dispatched Workers-line trip for the worker on ``driver``'s manifest,
        as the soonest upcoming ride. Returns the Dispatch Trip name."""
        driver = driver or self.driver
        tr, rp, dt = factories.make_worker_trip(
            driver,
            self.project,
            self.building,
            [self.worker],
            f"GPS Route {frappe.generate_hash(length=12)}",
            from_location="Building Gate",
            # [#fqdlds]
            pickup_datetime=frappe.utils.add_to_date(frappe.utils.now_datetime(), hours=2),
            passengers=1,
            # [#rbemo2]
            status="Dispatched",
            link_route_plan_on_request=True,
        )
        self.addCleanup(lambda: self._purge_trip(dt.name, rp.name, tr.name))
        return dt.name

    # [#s9nb6z]
    def test_next_ride_eta_is_computed(self):
        """Feed a driver GPS fix via the ingestion API, then assert Home's
        next_ride carries the exact server-computed ETA (15 min)."""
        self._assign_worker()
        dt = self._dispatched_trip()

        # [#p3w8qi]
        frappe.set_user(self.driver_email)
        result = driver_portal.push_driver_position(
            dispatch_trip=dt, lat=_DRIVER_LAT, lng=_DRIVER_LNG
        )
        self.assertEqual(result["driver_lat"], _DRIVER_LAT)
        self.assertEqual(result["driver_lng"], _DRIVER_LNG)
        self.assertIsNotNone(result["driver_position_updated_at"])
        frappe.set_user("Administrator")

        # [#brhu1s]
        self.assertEqual(frappe.db.get_value("Dispatch Trip", dt, "driver_lat"), _DRIVER_LAT)

        home = masar.get_worker_home(token=self.token)
        next_ride = home["next_ride"]
        self.assertIsNotNone(next_ride, "fixture sanity: the worker has a next ride")
        self.assertEqual(next_ride["dispatch_trip"], dt)
        # [#ito418]
        self.assertEqual(next_ride["eta_minutes"], _EXPECTED_ETA_MIN)

    def test_eta_is_none_without_a_position(self):
        """Non-vacuity guard: with the SAME fixture but no pushed GPS fix, the ETA
        is None — so the computation, not the fixture, produces the 15 above."""
        self._assign_worker()
        dt = self._dispatched_trip()
        home = masar.get_worker_home(token=self.token)
        self.assertEqual(home["next_ride"]["dispatch_trip"], dt)
        self.assertIsNone(home["next_ride"]["eta_minutes"])

    # [#ekocsg]
    def test_push_rejects_another_drivers_trip(self):
        """A driver may not write a position onto a trip that is not theirs — the
        ownership guard fails closed."""
        self._assign_worker()
        dt = self._dispatched_trip(driver=self.driver)  # [#7z0tvn]
        frappe.set_user(self.other_email)  # [#p9nnmp]
        with self.assertRaises(frappe.DoesNotExistError):
            driver_portal.push_driver_position(dispatch_trip=dt, lat=_DRIVER_LAT, lng=_DRIVER_LNG)
        frappe.set_user("Administrator")
        # [#4hfag4]
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

    # [#ktm872]
    def _purge_assignment(self, name):
        frappe.set_user("Administrator")
        if name and frappe.db.exists("Housing Assignment", name):
            doc = frappe.get_doc("Housing Assignment", name)
            if doc.docstatus == 1:
                try:
                    doc.cancel()
                except Exception:
                    pass
            frappe.delete_doc("Housing Assignment", name, ignore_permissions=True, force=True)

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


def tearDownModule():
    # This module commits (setUpClass/tearDownClass), so its Building survives
    # FrappeTestCase rollback; drop every Building created after the baseline (P-148).
    factories.purge_test_buildings()
