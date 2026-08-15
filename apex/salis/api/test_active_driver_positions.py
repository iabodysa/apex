# Copyright (c) 2026, AFMCO and contributors
"""Every driver on the supervisor's own assignments, in one paginated read.

``route_supervisor.get_active_driver_positions`` backs the yard map: one request for
today's Planned trips plus every still-Dispatched trip, so the map does not issue a
request per row.

Rewritten 2026-08-15. Every case here was a Silent-Pass, in three separate ways:

  * the endpoint returns a paginated ENVELOPE (``{"positions": [...], "start", ...}``),
    not a list. Four cases did ``for row in get_active_driver_positions()``, which
    iterates a dict and yields its five KEYS — so they looped over strings and graded
    nothing about any trip;
  * ``test_a_driver_with_no_fix_is_listed_rather_than_dropped`` asserted
    ``any(not p) or all(p)``, which is true for every possible list, including the empty
    one. A tautology cannot fail;
  * ``test_the_scope_is_the_callers_own_plans`` skipped unless a ``movement.demo@``
    user existed. It does not exist on ci.localhost, so it had never run, and it read a
    ``route_plan`` key the payload stopped carrying when the subject moved from Route
    Plan to Route Assignment.

The population is now built by the test instead of read off whatever the site happens
to hold, so a fresh site grades the same contract as a seeded one.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.salis.api.route_supervisor import (
    PLAN_PAGE_LENGTH,
    get_active_driver_positions,
)

# The row the map actually filters and draws on. Asserted as an exact set: a key added
# without this list moving is a key nothing grades, and a key removed is a map that
# renders undefined.
ROW_FIELDS = {
    "dispatch_trip", "route_assignment", "route_name", "project", "project_label",
    "status", "driver", "driver_name", "vehicle", "plate", "has_position", "lat",
    "lng", "updated_at", "age_seconds", "stale", "stops", "path",
}
ENVELOPE_FIELDS = {"positions", "start", "page_length", "returned", "has_more"}


class TestActiveDriverPositions(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.driver = frappe.get_doc(
            {
                "doctype": "Salis Driver",
                "full_name": f"ADP Driver {frappe.generate_hash(length=12)}",
                "status": "Active",
            }
        ).insert(ignore_permissions=True).name

    def setUp(self):
        frappe.set_user("Administrator")
        self.addCleanup(frappe.set_user, "Administrator")

    def _trip(self, status="Planned"):
        """One trip the endpoint must return: today's date and a listed status."""
        return frappe.get_doc(
            {
                "doctype": "Dispatch Trip",
                "driver": self.driver,
                "trip_date": frappe.utils.today(),
                "status": status,
            }
        ).insert(ignore_permissions=True).name

    def test_a_user_without_a_fleet_role_is_refused(self):
        """Built rather than looked up, so the refusal is graded on every site and not
        only where a demo fixture happens to exist."""
        from apex.tests._helpers import _user

        outsider = _user("adp_outsider@example.com", "Resident Supervisor")
        frappe.set_user(outsider)
        with self.assertRaises(frappe.PermissionError):
            get_active_driver_positions()

    def test_the_read_returns_a_paginated_envelope_around_the_rows(self):
        """The shape the map unpacks. Graded on a trip THIS test created, so the
        assertions below cannot pass by looping over an empty list."""
        name = self._trip()
        payload = get_active_driver_positions()

        self.assertEqual(set(payload), ENVELOPE_FIELDS)
        self.assertEqual(payload["page_length"], PLAN_PAGE_LENGTH)
        self.assertEqual(payload["returned"], len(payload["positions"]))

        rows = {row["dispatch_trip"]: row for row in payload["positions"]}
        self.assertIn(name, rows, "a Planned trip today must reach the map")
        self.assertEqual(set(rows[name]), ROW_FIELDS)

    def test_a_dispatched_trip_is_listed_whatever_its_date(self):
        """Planned is scoped to today; Dispatched is not, because a trip that is still
        running past midnight must not fall off the map.

        The status is reached by db_set, not by insert: the controller refuses any
        initial status but Planned (dispatch_trip.py:150), so a fixture that inserted
        Dispatched directly would die in validate rather than test the filter.
        """
        name = self._trip()
        frappe.db.set_value("Dispatch Trip", name, "status", "Dispatched")
        frappe.db.set_value(
            "Dispatch Trip", name, "trip_date", frappe.utils.add_days(frappe.utils.today(), -3)
        )
        listed = {
            row["dispatch_trip"] for row in get_active_driver_positions()["positions"]
        }
        self.assertIn(name, listed)

    def test_a_driver_with_no_fix_is_listed_and_pins_the_null_island_defect(self):
        """A driver with no fix must stay on the list — and today the map draws him at
        latitude 0, longitude 0.

        PINNED, not endorsed. Two live application defects meet in this row:

        1. ``has_position`` is derived as ``trip.driver_lat is not None and
           trip.driver_lng is not None`` (route_supervisor.py:174-176) from two **Float**
           fields. Frappe stores Float as NOT NULL DEFAULT 0, so driver_lat is 0.0 and
           never None — the predicate is TRUE for every trip that has never reported a
           position, and the map plots those drivers at Null Island. The sibling reader
           in masar_routes.py:93 gets this right with a truthiness check, so the app is
           inconsistent with itself rather than uniformly wrong.
        2. Nothing in the app writes driver_lat/driver_lng at all any more. The only
           writer was driver_portal.push_driver_position, removed with the rest of the
           retired portal surface, so 0.0 is now the ONLY value these columns ever hold.

        The assertions below state what the code does today. When either defect is
        fixed this case goes red, which is the point: it is the thing that tells you the
        other branch finally became reachable.
        """
        name = self._trip()
        row = next(
            r for r in get_active_driver_positions()["positions"]
            if r["dispatch_trip"] == name
        )
        self.assertEqual(row["lat"], 0.0, "Float columns are NOT NULL; a missing fix reads 0.0")
        self.assertEqual(row["lng"], 0.0)
        self.assertTrue(
            row["has_position"],
            "DEFECT PINNED: an `is not None` test on a Float can never be False",
        )
        self.assertIsNone(
            row["updated_at"], "the Datetime beside them IS nullable and stays empty"
        )
        self.assertIsNone(row["stale"], "no timestamp means no staleness verdict")

    def test_page_bounds_are_refused_rather_than_clamped(self):
        """A caller cannot ask for page zero, a negative offset, or a page wider than
        the published ceiling — an unbounded page_length is an unbounded query."""
        for start, page_length in ((-1, 10), (0, 0), (0, PLAN_PAGE_LENGTH + 1)):
            with self.subTest(start=start, page_length=page_length):
                with self.assertRaises(frappe.ValidationError):
                    get_active_driver_positions(start=start, page_length=page_length)

    def test_a_stop_reaches_the_map_only_with_both_coordinates(self):
        """The line is drawn from the stops, so a stop missing either coordinate must
        not arrive as a point at zero."""
        self._trip()
        for row in get_active_driver_positions()["positions"]:
            for stop in row["stops"]:
                self.assertTrue(stop["lat"] and stop["lng"], stop)
                self.assertIn("stop_name", stop)

    def test_the_road_geometry_is_never_half_drawn(self):
        """A router may be switched off, unreachable or slow; the row still arrives with
        an empty path. When it is there it is a list of [lat, lng] pairs, so a
        half-parsed answer cannot reach the map."""
        self._trip()
        for row in get_active_driver_positions()["positions"]:
            path = row["path"]
            self.assertIsInstance(path, list)
            for point in path:
                self.assertEqual(len(point), 2)
                self.assertIsInstance(point[0], float)
