# Copyright (c) 2026, afmcoltd
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

CACHE_TTL_SECONDS = 7 * 24 * 60 * 60
FAILURE_TTL_SECONDS = 5 * 60
REQUEST_TIMEOUT = 6


def _router_base():
    """Returns the configured OSRM routing server base URL, or the public default."""
    configured = frappe.conf.get("apex_routing_url", DEFAULT_ROUTER)
    return (configured or "").rstrip("/")


def _fingerprint(points):
    """Returns a stable hash of a stop-point list, used as its cache identity.

    The dump feeds the SHA-1 straight after; its bytes ARE the hash input, so a
    formatting change here (key order, separators) changes the fingerprint and
    silently splits one route's cache entries in two.
    """
    return hashlib.sha1(json.dumps(points, sort_keys=True).encode("utf-8")).hexdigest()


def _cache_key(points):
    """Returns the cache key under which a stop-point list's routed path is stored."""
    return f"{CACHE_KEY}:{_fingerprint(points)}"


def is_cached(points):
    """Whether ``points`` can be answered without touching the network.

    A caller drawing many routes uses this to spend its router budget on the ones that
    would actually call out — a warm route costs nothing and must not consume it.
    """
    if not points or len(points) < 2:
        return True
    return frappe.cache.get_value(_cache_key(points)) is not None


def _remember(points, path, ttl):
    """Store a routing answer under its own expiring key.

    One key per route, not a field in one shared Redis HASH via ``hset``: a hash field
    carries no TTL, so ``CACHE_TTL_SECONDS`` could not apply to it, and a router outage
    would cache the empty answer FOREVER — every later request for that route would draw
    no line until someone flushed Redis. One key per route makes the lifetime
    expressible, so a failure is forgotten in minutes and retried.
    """
    frappe.cache.set_value(_cache_key(points), path, expires_in_sec=ttl)


def road_path(points, cached_only=False):
    """Return the drive through ``points`` as [[lat, lng], ...], or None.

    ``points`` is the ordered stop list as (lat, lng) pairs. None means "no geometry" for
    every reason a caller cannot act on differently — routing switched off, fewer than two
    stops, the router unreachable, a malformed answer — and the map then draws the line it
    would have drawn anyway.

    ``cached_only`` answers from the cache or returns None without touching the network.
    A caller drawing MANY routes in one request needs it: each miss is a call to a public
    router with a ``REQUEST_TIMEOUT``-second ceiling, and a loop over plans turns that
    ceiling into a multiple of itself while a person waits. Spending a bounded budget on
    misses and serving the rest cached-only degrades the tail to straight lines, which is
    the same thing the caller already renders when the router is unreachable.

    The response is parsed as the OSRM server's own HTTP body, byte for byte — it is
    never client input, so there is no "already parsed" shape to guard against.
    """
    base = _router_base()
    if not base or not points or len(points) < 2:
        return None

    cached = frappe.cache.get_value(_cache_key(points))
    if cached is not None:
        return cached or None
    if cached_only:
        return None

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
