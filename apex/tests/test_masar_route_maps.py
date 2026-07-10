# Copyright (c) 2026, AFMCO and contributors
"""Masar full-route Maps deep-link helpers (pure, no DB).

Guards the worker-side ``_full_route_maps_url`` / ``_stop_waypoint`` contract so a
worker's trip view opens the SAME chained Google-Maps directions URL the driver
navigates: each ordered stop becomes a waypoint, resolved coords-first then a
``q=`` query then building+city then the stop's own location, the last stop is the
destination, and the intermediate waypoints are capped at nine.
"""


from frappe.tests.utils import FrappeTestCase

from apex.salis.api import driver_portal, maps_links, masar


def _stop(building_name=None, city=None, google_maps_url=None, location=None):
    pickup = None
    if building_name or city or google_maps_url:
        pickup = {"building_name": building_name, "city": city, "google_maps_url": google_maps_url}
    return {"pickup": pickup, "location": location}


class TestMasarRouteMaps(FrappeTestCase):
    def test_waypoint_prefers_coords_from_url(self):
        wp = masar._stop_waypoint(_stop(google_maps_url="https://maps.google.com/?q=24.7136,46.6753"))
        self.assertEqual(wp, "24.7136,46.6753")

    def test_waypoint_ignores_at_viewport_center(self):
        # A bare `@lat,lng` is the map-center (viewport), NOT the place — it must
        # not be grabbed; with nothing else navigable the stop resolves to None.
        wp = masar._stop_waypoint(_stop(google_maps_url="https://www.google.com/maps/@24.7,46.6,17z"))
        self.assertIsNone(wp)

    def test_waypoint_prefers_place_over_viewport_and_origin(self):
        # A complex share URL with a `/dir/<origin>` leg and an `@` viewport AND a
        # real place query must resolve to the PLACE (q=), not the decoy coords.
        url = "https://www.google.com/maps/dir/24.0,46.0/@24.5,46.5,12z/data=!4m2?q=24.7136,46.6753"
        wp = masar._stop_waypoint(_stop(google_maps_url=url))
        self.assertEqual(wp, "24.7136,46.6753")

    def test_waypoint_reads_place_embed_3d4d(self):
        url = "https://www.google.com/maps/place/X/@24.5,46.5,17z/data=!3d24.7136!4d46.6753"
        wp = masar._stop_waypoint(_stop(google_maps_url=url))
        self.assertEqual(wp, "24.7136,46.6753")

    def test_waypoint_clean_coord_url_unchanged(self):
        # A clean coordinate URL (no @ viewport / no /dir leg) still resolves the
        # bare lat,lng — behavior identical to before for simple links.
        wp = masar._stop_waypoint(_stop(google_maps_url="https://maps.app/loc/24.7,46.6"))
        self.assertEqual(wp, "24.7,46.6")

    def test_waypoint_falls_back_to_building_city(self):
        wp = masar._stop_waypoint(_stop(building_name="Block A", city="Riyadh"))
        self.assertEqual(wp, "Block%20A%2C%20Riyadh")

    def test_waypoint_falls_back_to_location(self):
        self.assertEqual(masar._stop_waypoint(_stop(location="Gate 3")), "Gate%203")

    def test_waypoint_none_when_nothing_navigable(self):
        self.assertIsNone(masar._stop_waypoint(_stop()))

    def test_full_route_none_below_two_stops(self):
        self.assertIsNone(masar._full_route_maps_url([]))
        self.assertIsNone(masar._full_route_maps_url([_stop(location="Only one")]))

    def test_full_route_chains_destination_and_waypoints(self):
        stops = [
            _stop(google_maps_url="https://maps.google.com/?q=24.1,46.1"),
            _stop(building_name="Mid", city="Riyadh"),
            _stop(location="Site"),
        ]
        url = masar._full_route_maps_url(stops)
        self.assertTrue(url.startswith("https://www.google.com/maps/dir/?api=1&destination=Site"))
        self.assertIn("waypoints=24.1,46.1|Mid%2C%20Riyadh", url)

    def test_full_route_caps_waypoints_at_nine(self):
        # 12 navigable stops -> last is destination, first 9 are kept as waypoints.
        stops = [_stop(location=f"S{i}") for i in range(12)]
        url = masar._full_route_maps_url(stops)
        self.assertEqual(url.count("|"), 8)  # 9 waypoints => 8 separators
        self.assertTrue(url.endswith("destination=S11&waypoints=" + "|".join(f"S{i}" for i in range(9))))

    def test_driver_and_worker_build_identical_url(self):
        # Both call sites must yield the SAME deep-link for the same ordered stops:
        # masar/maps_links chain a resolved list; driver_portal resolves a plan via
        # masar._ordered_stops first, then delegates to the same chainer.
        stops = [
            _stop(google_maps_url="https://maps.google.com/?q=24.1,46.1"),
            _stop(building_name="Mid", city="Riyadh"),
            _stop(location="Site"),
        ]
        original = masar._ordered_stops
        masar._ordered_stops = lambda _plan: stops
        try:
            driver_url = driver_portal._full_route_maps_url("ANY-PLAN")
        finally:
            masar._ordered_stops = original
        worker_url = masar._full_route_maps_url(stops)
        shared_url = maps_links._full_route_maps_url(stops)
        self.assertEqual(driver_url, worker_url)
        self.assertEqual(worker_url, shared_url)
        self.assertTrue(driver_url.startswith("https://www.google.com/maps/dir/?api=1&destination=Site"))

    def test_shared_module_is_single_source(self):
        # The dedup invariant: both modules expose the one shared builder, not copies.
        self.assertIs(masar._stop_waypoint, maps_links._stop_waypoint)
        self.assertIs(driver_portal._stop_waypoint, maps_links._stop_waypoint)
        self.assertIs(masar._full_route_maps_url, maps_links._full_route_maps_url)
