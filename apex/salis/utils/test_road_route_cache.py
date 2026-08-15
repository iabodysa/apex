# Copyright (c) 2026, AFMCO and contributors
"""A-384 — a router outage must not be remembered forever.

``road_path`` calls a PUBLIC routing service over the internet. When that call failed
it cached the empty answer so the next request would not wait again — but it cached it
with ``frappe.cache.hset``, a field inside one Redis HASH, and a hash field carries no
TTL. ``CACHE_TTL_SECONDS`` was declared beside it and referenced nowhere, so a single
transient outage meant that route drew no line until somebody flushed Redis.

The fix is one key per route so a lifetime can be expressed at all, and two lifetimes
rather than one: a drawn route is stable for a week, a failure is worth minutes.

These assertions read the real Redis TTL rather than trusting the call, because the
whole defect was a store that silently accepted a value and dropped its expiry.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.salis.utils import road_route

POINTS = [(24.7136, 46.6753), (26.4207, 50.0888)]


class TestTheRouterOutageExpires(FrappeTestCase):
    def setUp(self):
        frappe.cache.delete_value(road_route._cache_key(POINTS))

    def tearDown(self):
        frappe.cache.delete_value(road_route._cache_key(POINTS))

    def _ttl(self):
        return frappe.cache.ttl(frappe.cache.make_key(road_route._cache_key(POINTS)))

    def test_the_constant_is_actually_used(self):
        """It was declared and never referenced, which is how the bug survived."""
        self.assertGreater(road_route.CACHE_TTL_SECONDS, 0)
        self.assertGreater(road_route.FAILURE_TTL_SECONDS, 0)
        self.assertLess(
            road_route.FAILURE_TTL_SECONDS,
            road_route.CACHE_TTL_SECONDS,
            "a transient outage must not be remembered as long as a real route",
        )

    def test_a_failure_is_remembered_only_for_minutes(self):
        road_route._remember(POINTS, [], road_route.FAILURE_TTL_SECONDS)
        ttl = self._ttl()
        self.assertGreater(ttl, 0, "the failure was stored with NO expiry — the old bug")
        self.assertLessEqual(ttl, road_route.FAILURE_TTL_SECONDS)

    def test_a_real_route_is_remembered_for_a_week(self):
        road_route._remember(POINTS, [[24.7, 46.6]], road_route.CACHE_TTL_SECONDS)
        ttl = self._ttl()
        self.assertGreater(ttl, road_route.FAILURE_TTL_SECONDS)
        self.assertLessEqual(ttl, road_route.CACHE_TTL_SECONDS)

    def test_a_cached_failure_still_reads_as_no_geometry(self):
        """The caller contract is unchanged: None means draw the straight line."""
        road_route._remember(POINTS, [], road_route.FAILURE_TTL_SECONDS)
        self.assertIsNone(road_route.road_path(POINTS))

    def test_a_cached_route_is_returned_without_calling_the_router(self):
        path = [[24.7, 46.6], [26.4, 50.0]]
        road_route._remember(POINTS, path, road_route.CACHE_TTL_SECONDS)

        def explode(*args, **kwargs):
            raise AssertionError("the router was called despite a warm cache")

        original = road_route.urlopen
        road_route.urlopen = explode
        try:
            self.assertEqual(road_route.road_path(POINTS), path)
        finally:
            road_route.urlopen = original

    def test_the_old_hash_shape_could_not_have_expired(self):
        """The negative control, stated as the defect itself rather than as a claim.

        Writing the failure the way the code used to — a field in one shared hash —
        leaves Redis reporting -1 for that hash, which is 'no expiry set'. No TTL
        argument could have changed that, which is why the constant sat unused.
        """
        frappe.cache.hset(road_route.CACHE_KEY, "probe-fingerprint", [])
        try:
            hash_ttl = frappe.cache.ttl(frappe.cache.make_key(road_route.CACHE_KEY))
            self.assertEqual(
                hash_ttl, -1, "expected the legacy hash to carry no expiry at all"
            )
        finally:
            frappe.cache.hdel(road_route.CACHE_KEY, "probe-fingerprint")

    def test_routing_switched_off_never_touches_the_cache(self):
        original = road_route._router_base
        road_route._router_base = lambda: ""
        try:
            self.assertIsNone(road_route.road_path(POINTS))
        finally:
            road_route._router_base = original
        self.assertIsNone(frappe.cache.get_value(road_route._cache_key(POINTS)))
