# Copyright (c) 2026, afmcoltd
"""Regression: the Dispatch Trip document check must resolve the same project the
list fragment does.

``_render_trip`` grants a project-less trip whose ``route_plan`` belongs to an
allowed project — the historical-row fallback Salis keeps for trips raised before
Dispatch Trip carried its own ``project``. ``_doc_project`` did not follow that
fallback for Dispatch Trip, so the list showed such a trip and the form refused
it: the scoped supervisor read a row they could not open.

The fix is a Dispatch-Trip branch in ``_doc_project`` rather than a row in
``INDIRECT_PROJECT_SCOPED``, and ``test_doc_project_ignores_the_vehicle`` is why.
The generic indirect chain falls through to the doc's ``vehicle`` link; Dispatch
Trip HAS one, so listing it there would have resolved a vehicle's project the
fragment never grants and the document check would allow a row the list hides —
widening a deny-only rule.

Pure unit tests: the whole ``frappe.db`` handle is replaced, so no site and no
table.
"""

from __future__ import annotations

import unittest
from contextlib import contextmanager
from unittest import mock

import frappe

from apex.salis import permissions


SCOPED_USER = "supervisor@example.com"


def _trip(**fields):
    """A Dispatch Trip doc stand-in carrying no project of its own."""
    base = {
        "doctype": "Dispatch Trip",
        "project": None,
        "route_plan": None,
        "route_assignment": None,
        "driver": None,
        "vehicle": None,
        "owner": "someone-else@example.com",
    }
    base.update(fields)
    return frappe._dict(base)


@contextmanager
def _db(get_value_returns):
    """Replace the whole ``frappe.db`` handle — the attribute is an unbound proxy
    off-site, so it cannot be patched member by member."""
    db = mock.MagicMock()
    db.get_value.return_value = get_value_returns
    with mock.patch.object(permissions.frappe, "db", db):
        yield db


@contextmanager
def _scoped_to(projects):
    """A scoped, non-driver user holding exactly ``projects``."""
    with mock.patch.object(
        permissions, "_is_unscoped", return_value=False
    ), mock.patch.object(
        permissions, "get_driver_for_session_user", return_value=None
    ), mock.patch.object(
        permissions, "_allowed_projects_for", return_value=projects
    ):
        yield


class TestDispatchTripProjectFallback(unittest.TestCase):
    def test_doc_project_follows_the_historical_route_plan(self):
        """The same second hop ``_render_trip`` makes, made by the document check."""
        with _db("PROJ-1") as db:
            self.assertEqual(
                permissions._doc_project(_trip(route_plan="RP-OLD")), "PROJ-1"
            )
        db.get_value.assert_called_once_with("Route Plan", "RP-OLD", "project")

    def test_doc_project_ignores_the_vehicle(self):
        """``_render_trip`` never joins the vehicle, so neither may this.

        A trip with no project and no route plan is out of every scope. Resolving
        one through its vehicle would let the form open a row the list hides.
        """
        with _db("PROJ-1") as db:
            self.assertIsNone(permissions._doc_project(_trip(vehicle="VEH-1")))
        db.get_value.assert_not_called()

    def test_legacy_trip_in_an_allowed_project_is_not_refused(self):
        """The end-to-end refusal the defect produced: listed, then denied."""
        with _scoped_to(["PROJ-1"]), _db("PROJ-1"):
            verdict = permissions.project_scoped_has_permission(
                _trip(route_plan="RP-OLD"), "read", user=SCOPED_USER
            )
        self.assertIsNone(verdict, "a trip the list fragment shows must open")

    def test_legacy_trip_outside_scope_is_still_refused(self):
        """The fallback must not become a way in for another project's trip."""
        with _scoped_to(["PROJ-1"]), _db("PROJ-OTHER"):
            verdict = permissions.project_scoped_has_permission(
                _trip(route_plan="RP-OTHER"), "read", user=SCOPED_USER
            )
        self.assertFalse(verdict)


if __name__ == "__main__":
    unittest.main()
