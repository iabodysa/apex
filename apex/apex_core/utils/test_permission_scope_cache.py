# Copyright (c) 2026, afmcoltd
"""The per-user scope resolvers read frappe's User Permission resolver, not the table.

Every scoped Habitat / Salis permission check — the ``permission_query_conditions`` list
fragments, the ``has_permission`` form/submit guards, and the report-side
``report_*_scope`` re-application — funnels through ONE shared per-user resolver:

  * ``apex.habitat.permissions._allowed_buildings``  (Building User Permissions)
  * ``apex.salis.permissions._allowed_projects``     (Project User Permissions)

Both used to SELECT ``User Permission`` directly with ``pluck="for_value"`` and memoise the
result in ``frappe.local.cache``. That pluck returned the value and dropped every other
column — ``applicable_for`` included — so a permission granted for ONE doctype silently
applied to all of them. They now delegate to ``frappe.permissions.get_user_permissions``,
which returns the whole row, caches per user in Redis, and short-circuits Administrator and
Guest before any query.

These tests lock what is OURS in that arrangement:

  1. the resolvers go through the framework resolver and never re-query the table
     (the reinvention this replaced),
  2. the scope is per user — resolving User B never returns User A's values,
  3. the returned list is not aliased to the cached structure, so a caller mutating its
     result cannot corrupt another caller's scope.

Cache LIFETIME is frappe's own (``frappe.cache.hget("user_permissions", user)``, invalidated
by ``User Permission.on_update``) and is not re-tested here.

Nothing is inserted: the framework resolver is stubbed, so the identities are literals and
no User, User Permission or tenant record is built at all.
"""

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.habitat import permissions as HP
from apex.salis import permissions as SP


def _permission_rows(values):
    return [
        frappe._dict(doc=value, applicable_for=None, is_default=0, hide_descendants=0)
        for value in values
    ]


class _ScopeResolverMixin:
    """Shared assertions parametrised over a resolver + its User Permission rows.

    Subclasses set ``resolver`` (the module-level ``_allowed_*`` function), ``allow`` (the
    User Permission ``allow`` doctype it binds) and ``rows`` (a ``{user: [value, ...]}`` map
    the patched framework resolver serves).
    """

    resolver = None
    allow = None
    rows = None

    def _patched_resolver(self):
        """Serve self.rows through frappe's resolver, and fail on a direct table read."""
        rows = self.rows
        allow = self.allow

        def fake_get_user_permissions(user):
            return {allow: _permission_rows(rows.get(user, []))}

        def forbidden_get_all(doctype, *args, **kwargs):
            raise AssertionError(
                "the scope resolver re-queried %r instead of using "
                "frappe.permissions.get_user_permissions" % doctype
            )

        return (
            patch.object(
                frappe.permissions, "get_user_permissions", side_effect=fake_get_user_permissions
            ),
            patch.object(frappe, "get_all", side_effect=forbidden_get_all),
        )

    def test_resolves_through_the_framework_resolver(self):
        user = next(iter(self.rows))
        framework, no_table_read = self._patched_resolver()
        with framework as m, no_table_read:
            self.assertEqual(self.resolver(user), list(self.rows[user]))
        self.assertGreaterEqual(m.call_count, 1)

    def test_user_keyed_no_cross_user_bleed(self):
        users = list(self.rows)
        self.assertGreaterEqual(len(users), 2, "fixture needs two distinct users")
        a, b = users[0], users[1]
        framework, no_table_read = self._patched_resolver()
        with framework, no_table_read:
            scope_a = self.resolver(a)
            scope_b = self.resolver(b)
            self.assertEqual(scope_a, list(self.rows[a]))
            self.assertEqual(scope_b, list(self.rows[b]))
            self.assertNotEqual(scope_b, scope_a)
            self.assertEqual(self.resolver(a), list(self.rows[a]))

    def test_resolved_scope_is_not_aliased(self):
        user = next(iter(self.rows))
        framework, no_table_read = self._patched_resolver()
        with framework, no_table_read:
            resolved = self.resolver(user)
            resolved.append("INJECTED-NOT-IN-SCOPE")
            self.assertEqual(
                self.resolver(user),
                list(self.rows[user]),
                "mutating the returned scope list must not corrupt the resolved scope",
            )


class TestHabitatBuildingScopeResolver(_ScopeResolverMixin, FrappeTestCase):
    allow = "Building"
    rows = {
        "scoped-a@apex.test": ["Building-A1", "Building-A2"],
        "scoped-b@apex.test": ["Building-B1"],
    }

    @staticmethod
    def resolver(user):
        return HP._allowed_buildings(user)


class TestSalisProjectScopeResolver(_ScopeResolverMixin, FrappeTestCase):
    allow = "Project"
    rows = {
        "scoped-a@apex.test": ["Project-A1", "Project-A2"],
        "scoped-b@apex.test": ["Project-B1"],
    }

    @staticmethod
    def resolver(user):
        return SP._allowed_projects(user)
