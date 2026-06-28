# Copyright (c) 2026, AFMCO and contributors
"""Shared Google-Maps deep-link builders for the worker (masar) and driver routes.

Pure, no DB. Both the worker trip view (masar) and the driver portal must open the
IDENTICAL chained directions URL for the same ordered stops, so the waypoint
resolution + route-chaining live here once instead of being copied per call site.
"""


import re
from urllib.parse import quote


_COORD = r"(-?\d{1,3}\.\d+),\s*(-?\d{1,3}\.\d+)"
# The PLACE coordinate carriers, in preference order. A complex Google share URL
# can hold several lat,lng pairs; the place is the one in q=/query=/destination=
# or the !3dLAT!4dLNG embed, NOT the `@LAT,LNG` map-center (the viewport) nor the
# `/dir/<origin>` leg — grabbing either of those would resolve to the wrong point.
_PLACE_COORD_PATTERNS = (
    r"[?&](?:q|query|destination)=" + _COORD,  # q=/query=/destination=lat,lng
    r"!3d(-?\d{1,3}\.\d+)!4d(-?\d{1,3}\.\d+)",  # place embed !3dLAT!4dLNG
)


def _stop_waypoint(stop):
    """A Google-Maps-directions waypoint string for one ordered stop, or None.

    Prefers an exact ``lat,lng`` pair parsed from the stop's building
    ``google_maps_url`` — but only from a PLACE coordinate carrier (``q=`` /
    ``query=`` / ``destination=`` / the ``!3d..!4d`` embed), never the ``@lat,lng``
    map-center (viewport) or a ``/dir/<origin>`` leg of a complex share URL, which
    would point at the wrong spot. Falls back to a free-form ``q=`` text query in
    the URL, then a bare ``lat,lng`` only when the URL carries no ``@``/``/dir/``
    decoy (a clean coordinate link), then the building name + city as a place
    query, then the stop's own location text. Returns None when the stop carries
    nothing navigable, so it is skipped rather than breaking the chain."""
    pickup = stop.get("pickup") or {}
    url = pickup.get("google_maps_url") or ""
    # 1. A place coordinate (q=/query=/destination= or !3d!4d) -> exact spot.
    for pat in _PLACE_COORD_PATTERNS:
        m = re.search(pat, url)
        if m:
            return f"{m.group(1)},{m.group(2)}"
    # 2. A free-form q= place query (text, not coordinates).
    m = re.search(r"[?&]q=([^&]+)", url)
    if m:
        return m.group(1)
    # 3. A bare lat,lng ONLY on a clean coordinate URL — skip it when the URL also
    # carries a `@` viewport or a `/dir/` leg, since the bare pair would then be a
    # decoy (map-center / origin), not the place.
    if "@" not in url and "/dir/" not in url:
        m = re.search(rf"[?&=/]{_COORD}", url)
        if m:
            return f"{m.group(1)},{m.group(2)}"
    label = ", ".join(p for p in (pickup.get("building_name"), pickup.get("city")) if p)
    if label:
        return quote(label)
    if stop.get("location"):
        return quote(str(stop["location"]))
    return None


def _full_route_maps_url(stops):
    """A single Google Maps directions URL chaining every ordered stop as waypoints,
    or None when fewer than two stops are navigable.

    The last navigable stop is the ``destination``; the rest become ordered
    ``waypoints`` (Google caps these, so the chain is bounded at the first nine
    intermediate points -- still the whole short housing-pickup route in practice).
    Takes the already-resolved ordered-stops list (the exact sequence the Transport
    screen renders), so worker and driver deep-links match."""
    points = [wp for s in stops if (wp := _stop_waypoint(s))]
    if len(points) < 2:
        return None
    destination = points[-1]
    # Google Maps caps directions waypoints; keep the first nine intermediate stops.
    waypoints = points[:-1][:9]
    url = "https://www.google.com/maps/dir/?api=1&destination=" + destination
    if waypoints:
        url += "&waypoints=" + "|".join(waypoints)
    return url
