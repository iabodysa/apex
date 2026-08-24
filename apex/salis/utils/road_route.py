# Copyright (c) 2026, afmcoltd

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
    configured = frappe.conf.get("apex_routing_url", DEFAULT_ROUTER)
    return (configured or "").rstrip("/")


def _fingerprint(points):
    return hashlib.sha1(json.dumps(points, sort_keys=True).encode("utf-8")).hexdigest()


def _cache_key(points):
    return f"{CACHE_KEY}:{_fingerprint(points)}"


def is_cached(points):
    if not points or len(points) < 2:
        return True
    return frappe.cache.get_value(_cache_key(points)) is not None


def _remember(points, path, ttl):
    frappe.cache.set_value(_cache_key(points), path, expires_in_sec=ttl)


def road_path(points, cached_only=False):
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
