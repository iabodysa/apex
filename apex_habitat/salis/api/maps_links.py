"""Shared Google-Maps deep-link builders for the worker (masar) and driver routes.

Pure, no DB. Both the worker trip view (masar) and the driver portal must open the
IDENTICAL chained directions URL for the same ordered stops, so the waypoint
resolution + route-chaining live here once instead of being copied per call site.
"""


import re
from urllib.parse import quote


def _stop_waypoint(stop):
    """A Google-Maps-directions waypoint string for one ordered stop, or None.

    Prefers a ``lat,lng`` pair parsed from the stop's building ``google_maps_url``
    (the most precise destination), then a free-form ``q=`` query inside that URL,
    then the building name + city as a place query, then the stop's own location
    text. Returns None when the stop carries nothing navigable, so it is skipped
    rather than breaking the chain."""
    pickup = stop.get("pickup") or {}
    url = pickup.get("google_maps_url") or ""
    # @lat,lng or q=lat,lng embedded in a Google Maps link -> exact coordinates.
    m = re.search(r"[@?&=/](-?\d{1,3}\.\d+),(-?\d{1,3}\.\d+)", url)
    if m:
        return f"{m.group(1)},{m.group(2)}"
    m = re.search(r"[?&]q=([^&]+)", url)
    if m:
        return m.group(1)
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
