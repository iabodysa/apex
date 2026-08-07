# Copyright (c) 2026, AFMCO and contributors
"""Road geometry for a list of stops, so a route reads as a drive rather than a chord.

A straight line between two gates crosses whatever lies between them; a supervisor
comparing it to where the bus actually is cannot tell late from lost. The road shape comes
from an OSRM server — the same protocol erpnext reaches for with Google Directions in
Delivery Trip, minus the key and the billing.

WHERE IT CALLS, and how a deployment changes it: ``site_config.json`` key
``apex_routing_url``. Unset, it uses the public OSRM instance the OpenStreetMap community
runs, whose own policy caps a caller at roughly one request a second and offers no uptime
guarantee; a deployment that needs more runs its own OSRM and points this key at it. Set
it to an empty string to switch road geometry off entirely, and the map falls back to the
straight line it already draws.

WHAT LEAVES THE SITE: the stop coordinates, nothing else — no plan name, no project, no
driver. The call is made by the SERVER once per distinct stop list and cached, so a
portal's browsers never talk to the router and a poll every fifteen seconds costs nothing.
"""

import hashlib
import json
from urllib.parse import quote
from urllib.request import Request, urlopen

import frappe

DEFAULT_ROUTER = "https://routing.openstreetmap.de/routed-car"
CACHE_KEY = "apex_road_route"

# A drawn route between fixed points does not change, so a hit is worth keeping for a
# week. A FAILURE is not worth keeping at all beyond a moment: the router is a public
# service reached over the internet, and its outages are transient. These are two
# different lifetimes and they were previously one — see _remember below.
CACHE_TTL_SECONDS = 7 * 24 * 60 * 60
FAILURE_TTL_SECONDS = 5 * 60
REQUEST_TIMEOUT = 6


def _router_base():
    configured = frappe.conf.get("apex_routing_url", DEFAULT_ROUTER)
    return (configured or "").rstrip("/")


def _fingerprint(points):
    return hashlib.sha1(json.dumps(points, sort_keys=True).encode("utf-8")).hexdigest()


def _cache_key(points):
    return f"{CACHE_KEY}:{_fingerprint(points)}"


def _remember(points, path, ttl):
    """Store a routing answer under its own expiring key.

    It used to be a field in one Redis HASH via ``hset``. A hash field carries no TTL,
    so ``CACHE_TTL_SECONDS`` could not be applied to it and was never referenced — which
    meant a router outage cached the empty answer FOREVER, and every later request for
    that route drew no line until someone flushed Redis. One key per route makes the
    lifetime expressible, so a failure is forgotten in minutes and retried.
    """
    frappe.cache.set_value(_cache_key(points), path, expires_in_sec=ttl)


def road_path(points):
    """Return the drive through ``points`` as [[lat, lng], ...], or None.

    ``points`` is the ordered stop list as (lat, lng) pairs. None means "no geometry" for
    every reason a caller cannot act on differently — routing switched off, fewer than two
    stops, the router unreachable, a malformed answer — and the map then draws the line it
    would have drawn anyway.
    """
    base = _router_base()
    if not base or not points or len(points) < 2:
        return None

    cached = frappe.cache.get_value(_cache_key(points))
    if cached is not None:
        return cached or None

    coordinates = ";".join(f"{lng},{lat}" for lat, lng in points)
    url = f"{base}/route/v1/driving/{quote(coordinates)}?overview=full&geometries=geojson"
    try:
        request = Request(url, headers={"User-Agent": "apex-fleet-map"})
        with urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        _remember(points, [], FAILURE_TTL_SECONDS)
        return None

    if payload.get("code") != "Ok" or not payload.get("routes"):
        _remember(points, [], FAILURE_TTL_SECONDS)
        return None

    geometry = payload["routes"][0].get("geometry", {}).get("coordinates") or []
    path = [[point[1], point[0]] for point in geometry]
    _remember(points, path, CACHE_TTL_SECONDS)
    return path or None
