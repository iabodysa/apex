# Copyright (c) 2026, AFMCO and contributors
"""Request-scoped caching of the per-user permission scope resolvers.

Every scoped Habitat / Salis permission check — the ``permission_query_conditions``
list fragments, the ``has_permission`` form/submit guards, and the report-side
``report_*_scope`` re-application — funnels through ONE shared per-user resolver:

  * ``apex.habitat.permissions._allowed_buildings``  (Building User Permissions)
  * ``apex.salis.permissions._allowed_projects``     (Project User Permissions)

Before caching, each of those ran a fresh ``User Permission`` SQL query on EVERY
call, so rendering a list of N rows or a report issued N identical queries. Both
resolvers now wrap the query in ``frappe.local_cache(namespace, user, generator)``,
so the scope is resolved with at most ONE SQL per (request context, user).

These tests exercise the REAL ``frappe.local_cache`` and REAL ``frappe.set_user``
(no fake framework), patching only ``frappe.get_all`` to COUNT the underlying SQL
resolutions. They lock in three properties:

  1. Cache hit — a second resolve for the same user in one request issues no new
     query (``call_count == 1``).  [the "at most 1 SQL per request context" goal]
  2. User-keyed, no cross-user bleed — the cache key is the user, so resolving
     User B never returns User A's cached scope; each distinct user costs exactly
     one query.  [the security invariant]
  3. ``frappe.set_user`` clears the request cache — a background job that switches
     identity mid-run (``frappe.set_user``) starts from an empty
     ``frappe.local.cache`` and re-resolves for the new user, so a stale scope from
     the previous user can never be served.  [defence-in-depth on the invariant]

Runtime SQL-count proof (integrator): with a scoped user seeded a real Building /
Project User Permission, run a list view / the affected report under
``frappe-bench``'s query recorder (``frappe.db.sql`` logging or
``frappe.recorder``) and confirm exactly one ``tabUser Permission`` SELECT per
request for the scope, versus one-per-row before this change.
"""

import unittest
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.habitat import permissions as HP
from apex.salis import permissions as SP


class _ScopeCacheMixin:
    """Shared assertions parametrised over a resolver + its User Permission rows.

    Subclasses set ``resolver`` (the module-level ``_allowed_*`` function) and
    ``rows`` (a ``{user: [scope, ...]}`` map the patched ``frappe.get_all``
    returns, keyed on the ``filters['user']`` the resolver passes).
    """

    resolver = None
    rows = None

    def setUp(self):
        # Start every test with an empty request-local cache so counts are clean.
        frappe.local.cache = {}

    def tearDown(self):
        frappe.set_user("Administrator")
        frappe.local.cache = {}

    def _patched_get_all(self):
        """Patch frappe.get_all to serve self.rows by the queried user and count calls."""
        rows = self.rows

        def fake_get_all(doctype, filters=None, pluck=None, **kwargs):
            # Mirror the real signature the resolvers use.
            assert doctype == "User Permission"
            return list(rows[filters["user"]])

        return patch.object(frappe, "get_all", side_effect=fake_get_all)

    # 1. Cache hit: one SQL per request context for a repeated resolve.
    def test_single_sql_per_request_context(self):
        user = next(iter(self.rows))
        with self._patched_get_all() as m:
            first = self.resolver(user)
            second = self.resolver(user)
        self.assertEqual(first, list(self.rows[user]))
        self.assertEqual(second, list(self.rows[user]))
        self.assertEqual(
            m.call_count,
            1,
            "second resolve in the same request must be served from frappe.local cache",
        )

    # 2. User-keyed: no cross-user bleed, one SQL per distinct user.
    def test_user_keyed_no_cross_user_bleed(self):
        users = list(self.rows)
        self.assertGreaterEqual(len(users), 2, "fixture needs two distinct users")
        a, b = users[0], users[1]
        with self._patched_get_all() as m:
            scope_a = self.resolver(a)
            scope_b = self.resolver(b)
            scope_a_again = self.resolver(a)
            scope_b_again = self.resolver(b)
        self.assertEqual(scope_a, list(self.rows[a]))
        self.assertEqual(scope_b, list(self.rows[b]))
        # The security invariant: User B never receives User A's cached scope.
        self.assertNotEqual(scope_b, scope_a)
        self.assertEqual(scope_a_again, list(self.rows[a]))
        self.assertEqual(scope_b_again, list(self.rows[b]))
        self.assertEqual(
            m.call_count,
            2,
            "exactly one query per distinct user, then both served from cache",
        )

    # 3. frappe.set_user clears the request cache (background-job identity switch).
    def test_set_user_clears_request_scope_cache(self):
        users = list(self.rows)
        a, b = users[0], users[1]
        with self._patched_get_all():
            frappe.set_user(a)
            self.assertEqual(self.resolver(a), list(self.rows[a]))
            # The resolver populated the request cache under some namespace.
            self.assertTrue(frappe.local.cache, "resolver should have cached something")

            # A background job switches identity mid-run.
            frappe.set_user(b)
            self.assertEqual(
                frappe.local.cache,
                {},
                "frappe.set_user must reset frappe.local.cache so no scope bleeds across users",
            )
            # The next resolve returns the NEW user's scope, never the previous user's.
            self.assertEqual(self.resolver(b), list(self.rows[b]))

    # 4. The returned list is a copy: a caller mutating it cannot corrupt the cache.
    def test_resolved_scope_is_not_aliased(self):
        user = next(iter(self.rows))
        with self._patched_get_all():
            resolved = self.resolver(user)
            resolved.append("INJECTED-NOT-IN-SCOPE")
            re_resolved = self.resolver(user)
        self.assertEqual(
            re_resolved,
            list(self.rows[user]),
            "mutating the returned scope list must not corrupt the cached scope",
        )


class TestHabitatBuildingScopeCache(_ScopeCacheMixin, FrappeTestCase):
    rows = {
        "scoped-a@apex.test": ["Building-A1", "Building-A2"],
        "scoped-b@apex.test": ["Building-B1"],
    }

    @staticmethod
    def resolver(user):
        return HP._allowed_buildings(user)


class TestSalisProjectScopeCache(_ScopeCacheMixin, FrappeTestCase):
    rows = {
        "scoped-a@apex.test": ["Project-A1", "Project-A2"],
        "scoped-b@apex.test": ["Project-B1"],
    }

    @staticmethod
    def resolver(user):
        return SP._allowed_projects(user)


if __name__ == "__main__":
    unittest.main()
