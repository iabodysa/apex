# Copyright (c) 2026, afmcoltd
"""Coverage for the shared Google-Maps deep-link builder
(``apex.salis.api.maps_links``).

Both callables are pure (no DB, no whitelisting): ``_stop_waypoint`` resolves one
ordered stop to a Maps waypoint string, in its documented precedence order (an
exact PLACE coordinate first, never the ``@lat,lng`` viewport or a ``/dir/`` leg;
then a free-form ``q=`` text query; then a bare coordinate only on a clean link;
then a building-name+city label; then the stop's own location text; else None).
``_full_route_maps_url`` chains the resolved waypoints of every stop into one
directions URL, with the last navigable stop as ``destination`` and the rest as
``waypoints``, capped at nine and never silently dropping a resolvable stop short
of that cap.
"""

from __future__ import annotations

from frappe.tests.utils import FrappeTestCase

from apex.salis.api.maps_links import _full_route_maps_url, _stop_waypoint


def _stop(url=None, building_name=None, city=None, location=None):
    """An ordered-stop dict shaped exactly as the Transport screen renders it."""
    pickup = {}
    if url is not None:
        pickup["google_maps_url"] = url
    if building_name is not None:
        pickup["building_name"] = building_name
    if city is not None:
        pickup["city"] = city
    stop = {"pickup": pickup}
    if location is not None:
        stop["location"] = location
    return stop


class TestStopWaypoint(FrappeTestCase):
    """One ordered stop resolved to a Maps waypoint string, in precedence order."""

    def test_prefers_place_query_coordinate_over_viewport_center(self):
        """A ``?q=`` PLACE coordinate wins even when the same URL also carries an
        ``@lat,lng`` viewport center — the viewport is never a coordinate source."""
        url = "https://maps.google.com/@24.000000,45.000000,15z?q=24.774265,46.738586"
        self.assertEqual(_stop_waypoint(_stop(url=url)), "24.774265,46.738586")

    def test_prefers_the_3d4d_share_embed_when_no_query_param(self):
        """A share-link's ``!3d..!4d`` embed is read when no ``q=``/``destination=``
        param is present."""
        url = "https://www.google.com/maps/place/X/@24.0,45.0,15z/data=!4m5!3m4!1s0x0!8m2!3d24.774265!4d46.738586"
        self.assertEqual(_stop_waypoint(_stop(url=url)), "24.774265,46.738586")

    def test_falls_back_to_free_form_query_text(self):
        """No coordinate pattern matches, so the raw ``q=`` text is used as-is."""
        url = "https://maps.google.com/maps?q=Riyadh+Tower"
        self.assertEqual(_stop_waypoint(_stop(url=url)), "Riyadh+Tower")

    def test_bare_coordinate_accepted_on_a_clean_link(self):
        """A link with no ``@``/``/dir/`` decoy and no query param still yields its
        bare ``lat,lng``."""
        url = "https://maps.google.com/24.774265,46.738586"
        self.assertEqual(_stop_waypoint(_stop(url=url)), "24.774265,46.738586")

    def test_bare_coordinate_rejected_when_an_at_sign_decoy_is_present(self):
        """The same bare-coordinate shape is refused once the URL carries an
        ``@`` — it could be the wrong (viewport) coordinate — and the stop falls
        through to its label instead."""
        url = "https://maps.google.com/@24.774265,46.738586,15z"
        self.assertEqual(
            _stop_waypoint(_stop(url=url, building_name="Camp One", city="Jubail")),
            "Camp%20One%2C%20Jubail",
        )

    def test_falls_back_to_building_name_and_city_label(self):
        """No usable URL at all: the building name plus city becomes a quoted
        place query."""
        self.assertEqual(
            _stop_waypoint(_stop(building_name="Camp One", city="Jubail")),
            "Camp%20One%2C%20Jubail",
        )

    def test_falls_back_to_the_stops_own_location_text(self):
        """No pickup building at all: the stop's own free-text location is used,
        quoted for the URL."""
        self.assertEqual(_stop_waypoint({"pickup": {}, "location": "Gate 4"}), "Gate%204")

    def test_returns_none_when_the_stop_carries_nothing_navigable(self):
        """An empty stop resolves to None so the chain can skip it rather than
        break."""
        self.assertIsNone(_stop_waypoint({"pickup": {}}))
        self.assertIsNone(_stop_waypoint({}))


class TestFullRouteMapsUrl(FrappeTestCase):
    """The full chained directions URL across every ordered stop."""

    def _coord_stop(self, lat, lng):
        return _stop(url=f"https://maps.google.com/?q={lat},{lng}")

    def test_none_when_fewer_than_two_stops_are_navigable(self):
        """One navigable stop (or zero) cannot form a route — no destination
        without at least an origin-equivalent waypoint."""
        self.assertIsNone(_full_route_maps_url([]))
        self.assertIsNone(_full_route_maps_url([self._coord_stop("24.0", "45.0")]))
        self.assertIsNone(
            _full_route_maps_url([self._coord_stop("24.0", "45.0"), {"pickup": {}}])
        )

    def test_chains_every_stop_and_omits_nothing_the_map_needs(self):
        """Every resolvable stop lands in the URL: the last as ``destination``,
        the rest as pipe-joined ``waypoints`` — nothing dropped, api=1 pinned."""
        stops = [
            self._coord_stop("24.774265", "46.738586"),
            self._coord_stop("24.800000", "46.800000"),
            self._coord_stop("24.900000", "46.900000"),
        ]
        url = _full_route_maps_url(stops)
        self.assertTrue(url.startswith("https://www.google.com/maps/dir/?api=1&destination="))
        self.assertIn("destination=24.900000,46.900000", url)
        self.assertIn("waypoints=24.774265,46.738586|24.800000,46.800000", url)

    def test_two_stops_still_carries_one_waypoint(self):
        """Exactly two navigable stops still produce a ``waypoints`` param
        holding the first stop, not just a bare destination."""
        stops = [self._coord_stop("24.0", "45.0"), self._coord_stop("25.0", "46.0")]
        url = _full_route_maps_url(stops)
        self.assertIn("destination=25.0,46.0", url)
        self.assertIn("waypoints=24.0,45.0", url)

    def test_waypoints_are_capped_at_nine_intermediate_points(self):
        """Google caps intermediate waypoints at nine; the tenth and eleventh
        navigable stop (neither destination nor within the cap) are dropped."""
        stops = [self._coord_stop(f"{10 + i}.000001", f"{20 + i}.000001") for i in range(12)]
        url = _full_route_maps_url(stops)

        self.assertIn("destination=21.000001,31.000001", url)
        waypoints_part = url.split("waypoints=", 1)[1]
        waypoint_list = waypoints_part.split("|")
        self.assertEqual(len(waypoint_list), 9)
        self.assertEqual(waypoint_list[0], "10.000001,20.000001")
        self.assertEqual(waypoint_list[-1], "18.000001,28.000001")
        self.assertNotIn("19.000001,29.000001", url)
        self.assertNotIn("20.000001,30.000001", url)

    def test_an_unresolvable_stop_in_the_middle_is_skipped_not_fatal(self):
        """A stop with nothing navigable is dropped from the chain silently; the
        route still forms from the stops on either side of it."""
        stops = [self._coord_stop("24.0", "45.0"), {"pickup": {}}, self._coord_stop("25.0", "46.0")]
        url = _full_route_maps_url(stops)
        self.assertIn("destination=25.0,46.0", url)
        self.assertIn("waypoints=24.0,45.0", url)
