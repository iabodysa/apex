# Copyright (c) 2026, afmcoltd
"""Every project-scoped Salis DocType is wired on BOTH sides, or it is scoped on neither.

A DocType narrows to the acting user's projects only when three places agree: it has a
row in ``SALIS_SCOPE``, it is listed in ``permission_query_conditions`` (which narrows
the list view and ``/api/resource``), and it is listed in ``has_permission`` (which
narrows the single document). Miss one and the failure is silent — the desk list simply
returns every project's rows, with no error to notice.

Six DocTypes were missing from all three at once, among them Transport Trip Rating,
which grants read and write to the Worker role. Nothing detected it, because nothing
compared the three lists.
"""

from __future__ import annotations

import unittest

from apex import hooks
from apex.salis.permissions import SALIS_SCOPE

QUERY = "apex.salis.permissions.project_scope_query"
CHECK = "apex.salis.permissions.project_scoped_has_permission"


def _wired(mapping, target):
    return {
        doctype
        for doctype, handler in mapping.items()
        if (handler if isinstance(handler, str) else "") == target
    }


class TestSalisScopeWiring(unittest.TestCase):
    def test_the_scope_table_and_the_two_hooks_name_the_same_doctypes(self):
        scoped = set(SALIS_SCOPE)
        in_query = _wired(hooks.permission_query_conditions, QUERY)
        in_check = _wired(hooks.has_permission, CHECK)

        self.assertEqual(
            scoped - in_query,
            set(),
            "scoped in SALIS_SCOPE but absent from permission_query_conditions — "
            "the list view and /api/resource return every project's rows",
        )
        self.assertEqual(
            scoped - in_check,
            set(),
            "scoped in SALIS_SCOPE but absent from has_permission — "
            "the single document opens for any project",
        )
        self.assertEqual(
            in_query - scoped,
            set(),
            "wired to the Salis query hook with no row in SALIS_SCOPE",
        )
        self.assertEqual(
            in_check - scoped,
            set(),
            "wired to the Salis document hook with no row in SALIS_SCOPE",
        )

    def test_the_five_vehicle_anchored_doctypes_are_scoped(self):
        # Named individually because all five were readable across every project by a
        # Fleet Supervisor. A set comparison alone would pass again the day someone drops
        # one row from all three places at once.
        for doctype in (
            "Vehicle Handover",
            "Wash Request",
            "Fuel Daily Log",
            "Rental Vehicle Movement",
            "Movement Cost Recovery",
        ):
            with self.subTest(doctype=doctype):
                self.assertIn(doctype, SALIS_SCOPE)
                self.assertEqual(hooks.permission_query_conditions.get(doctype), QUERY)
                self.assertEqual(hooks.has_permission.get(doctype), CHECK)

    def test_transport_trip_rating_stays_unscoped_until_the_worker_has_a_project(self):
        # The sixth project-anchored DocType, held out on purpose and pinned here so the
        # omission reads as a decision rather than an oversight. Scoping it closes a real
        # cross-project read, and also closes the WRITE: the ownership branch of
        # _owner_or_project_has_permission is skipped on an unsaved row, and the portal
        # Worker capacity carries no Project User Permission to anchor to instead, so
        # every rating would fail closed on create. This case flips the day that capacity
        # gains a project — which is the signal to scope the DocType in the same change.
        self.assertNotIn("Transport Trip Rating", SALIS_SCOPE)
        self.assertIsNone(hooks.permission_query_conditions.get("Transport Trip Rating"))
        self.assertIsNone(hooks.has_permission.get("Transport Trip Rating"))
