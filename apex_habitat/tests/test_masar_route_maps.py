"""Masar full-route Maps deep-link helpers (pure, no DB).

Guards the worker-side ``_full_route_maps_url`` / ``_stop_waypoint`` contract so a
worker's trip view opens the SAME chained Google-Maps directions URL the driver
navigates: each ordered stop becomes a waypoint, resolved coords-first then a
``q=`` query then building+city then the stop's own location, the last stop is the
destination, and the intermediate waypoints are capped at nine.
"""


from frappe.tests.utils import FrappeTestCase

from apex_habitat.salis.api import masar


def _stop(building_name=None, city=None, google_maps_url=None, location=None):
    pickup = None
    if building_name or city or google_maps_url:
        pickup = {"building_name": building_name, "city": city, "google_maps_url": google_maps_url}
    return {"pickup": pickup, "location": location}


class TestMasarRouteMaps(FrappeTestCase):
    def test_waypoint_prefers_coords_from_url(self):
        wp = masar._stop_waypoint(_stop(google_maps_url="https://maps.google.com/?q=24.7136,46.6753"))
        self.assertEqual(wp, "24.7136,46.6753")

    def test_waypoint_at_coords(self):
        wp = masar._stop_waypoint(_stop(google_maps_url="https://www.google.com/maps/@24.7,46.6,17z"))
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
