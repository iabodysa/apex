# Copyright (c) 2026, afmcoltd


import re
from urllib.parse import quote


_COORD = r"(-?\d{1,3}\.\d+),\s*(-?\d{1,3}\.\d+)"
_PLACE_COORD_PATTERNS = (
    r"[?&](?:q|query|destination)=" + _COORD,
    r"!3d(-?\d{1,3}\.\d+)!4d(-?\d{1,3}\.\d+)",
)


def _stop_waypoint(stop):
    pickup = stop.get("pickup") or {}
    url = pickup.get("google_maps_url") or ""
    for pat in _PLACE_COORD_PATTERNS:
        m = re.search(pat, url)
        if m:
            return f"{m.group(1)},{m.group(2)}"
    m = re.search(r"[?&]q=([^&]+)", url)
    if m:
        return m.group(1)
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
    points = [wp for s in stops if (wp := _stop_waypoint(s))]
    if len(points) < 2:
        return None
    destination = points[-1]
    waypoints = points[:-1][:9]
    url = "https://www.google.com/maps/dir/?api=1&destination=" + destination
    if waypoints:
        url += "&waypoints=" + "|".join(waypoints)
    return url
