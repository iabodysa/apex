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
    def test_waypoint_extracts_from_url_by_documented_precedence(self):
        """_stop_waypoint reads a stop's google_maps_url by a fixed priority:
        an explicit q= place, over a bare viewport center, over a place/data
        embed, over an already-clean coordinate pair."""
        self.assertEqual(
            masar._stop_waypoint(
                _stop(google_maps_url="https://maps.google.com/?q=24.7136,46.6753")
            ),
            "24.7136,46.6753",
            "prefers a q= place over everything else",
        )
        self.assertIsNone(
            masar._stop_waypoint(
                _stop(google_maps_url="https://www.google.com/maps/@24.7,46.6,17z")
            ),
            "ignores a bare @lat,lng viewport center",
        )
        self.assertEqual(
            masar._stop_waypoint(
                _stop(
                    google_maps_url=(
                        "https://www.google.com/maps/dir/24.0,46.0/@24.5,46.5,12z/"
                        "data=!4m2?q=24.7136,46.6753"
                    )
                )
            ),
            "24.7136,46.6753",
            "prefers the place query over both viewport and origin",
        )
        self.assertEqual(
            masar._stop_waypoint(
                _stop(
                    google_maps_url=(
                        "https://www.google.com/maps/place/X/@24.5,46.5,17z/"
                        "data=!3d24.7136!4d46.6753"
                    )
                )
            ),
            "24.7136,46.6753",
            "reads coords out of a place embed's !3d!4d pair",
        )
        self.assertEqual(
            masar._stop_waypoint(_stop(google_maps_url="https://maps.app/loc/24.7,46.6")),
            "24.7,46.6",
            "leaves an already-clean coordinate URL unchanged",
        )

    def test_waypoint_falls_back_when_no_navigable_url(self):
        """With no usable google_maps_url, _stop_waypoint falls back to
        building+city, then the stop's raw location, then gives up."""
        self.assertEqual(
            masar._stop_waypoint(_stop(building_name="Block A", city="Riyadh")),
            "Block%20A%2C%20Riyadh",
            "building+city is the first fallback",
        )
        self.assertEqual(
            masar._stop_waypoint(_stop(location="Gate 3")),
            "Gate%203",
            "the stop's own location is the second fallback",
        )
        self.assertIsNone(
            masar._stop_waypoint(_stop()),
            "nothing navigable resolves to no waypoint",
        )

    def test_full_route_maps_url_follows_its_build_rules(self):
        """_full_route_maps_url refuses under two stops, chains destination +
        waypoints for a normal route, and caps intermediate waypoints at nine."""
        self.assertIsNone(
            masar._full_route_maps_url([]), "an empty stop list has no route"
        )
        self.assertIsNone(
            masar._full_route_maps_url([_stop(location="Only one")]),
            "a single stop has no route to build",
        )

        stops = [
            _stop(google_maps_url="https://maps.google.com/?q=24.1,46.1"),
            _stop(building_name="Mid", city="Riyadh"),
            _stop(location="Site"),
        ]
        url = masar._full_route_maps_url(stops)
        self.assertTrue(
            url.startswith("https://www.google.com/maps/dir/?api=1&destination=Site"),
            "the last stop becomes the destination",
        )
        self.assertIn(
            "waypoints=24.1,46.1|Mid%2C%20Riyadh",
            url,
            "the earlier stops chain in as ordered waypoints",
        )

        capped_stops = [_stop(location=f"S{i}") for i in range(12)]
        capped_url = masar._full_route_maps_url(capped_stops)
        self.assertEqual(
            capped_url.count("|"),
            8,
            "twelve stops must still cap at nine waypoints (eight separators)",
        )
        self.assertTrue(
            capped_url.endswith(
                "destination=S11&waypoints=" + "|".join(f"S{i}" for i in range(9))
            ),
            "the cap keeps only the first nine intermediate stops",
        )

    def test_shared_routing_module_is_the_single_source(self):
        """The driver and worker paths are not two implementations that
        happen to agree: they are literally the same functions, and produce
        the literal same URL for the same stops."""
        self.assertIs(
            masar._stop_waypoint, maps_links._stop_waypoint, "masar shares _stop_waypoint"
        )
        self.assertIs(
            driver_portal._stop_waypoint,
            maps_links._stop_waypoint,
            "driver_portal shares _stop_waypoint",
        )
        self.assertIs(
            masar._full_route_maps_url,
            maps_links._full_route_maps_url,
            "masar shares _full_route_maps_url",
        )
        self.assertIs(
            driver_portal._chain_route_maps_url,
            maps_links._full_route_maps_url,
            "driver_portal's chain alias shares _full_route_maps_url",
        )

        stops = [
            _stop(google_maps_url="https://maps.google.com/?q=24.1,46.1"),
            _stop(building_name="Mid", city="Riyadh"),
            _stop(location="Site"),
        ]
        original = masar._ordered_trip_stops
        masar._ordered_trip_stops = lambda _trip, _plan=None: stops
        try:
            driver_url = driver_portal._trip_route_maps_url("ANY-TRIP")
        finally:
            masar._ordered_trip_stops = original
        worker_url = masar._full_route_maps_url(stops)
        shared_url = maps_links._full_route_maps_url(stops)
        self.assertEqual(driver_url, worker_url, "the driver path matches the worker path")
        self.assertEqual(
            worker_url, shared_url, "the worker path matches the shared module directly"
        )
        self.assertTrue(
            driver_url.startswith("https://www.google.com/maps/dir/?api=1&destination=Site"),
            "the shared build still starts with the destination URL shape",
        )
