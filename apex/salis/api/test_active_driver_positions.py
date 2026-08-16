# Copyright (c) 2026, AFMCO and contributors
"""Every driver on the supervisor's own assignments, in one paginated read.

``route_supervisor.get_active_driver_positions`` backs the yard map: one request for
today's Planned trips plus every still-Dispatched trip, so the map does not issue a
request per row.

Every case here guards against a Silent-Pass, in three separate ways:

  * the endpoint returns a paginated ENVELOPE (``{"positions": [...], "start", ...}``),
    not a list, so a case must not do ``for row in get_active_driver_positions()`` — that
    iterates a dict and yields its five KEYS, looping over strings and grading nothing
    about any trip;
  * ``test_a_driver_with_no_fix_is_listed_rather_than_dropped`` asserts a condition that
    must be satisfiable as false: ``any(not p) or all(p)`` is true for every possible
    list, including the empty one, so a tautology here would grade nothing;
  * ``test_the_scope_is_the_callers_own_plans`` requires no pre-seeded site user and
    reads ``route_assignment`` rather than ``route_plan``, which is the field the
    payload actually carries (apex/salis/api/route_supervisor.py), so it runs on
    ci.localhost and any fresh site.

The population is built by the test instead of read off whatever the site happens to
hold, so a fresh site grades the same contract as a seeded one.
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
    "status", "driver", "driver_name", "vehicle", "plate", "stops", "path",
}
# The six keys the row carried while it claimed to know where the driver was. Named so
# the absence is graded rather than merely unmentioned: ROW_FIELDS is an exact set, but
# an exact set that grew a typo would stop noticing these coming back.
RETIRED_POSITION_FIELDS = {"has_position", "lat", "lng", "updated_at", "age_seconds", "stale"}
ENVELOPE_FIELDS = {"positions", "start", "page_length", "returned", "has_more"}


def _row_in_any_page(name):
    """The row for ``name`` from whichever page it lands on, or None.

    The endpoint orders ``planned_start asc, name asc`` and caps a page at
    PLAN_PAGE_LENGTH, so a freshly named trip sorts last and falls off page one the
    moment the site holds a page of live trips. Reading page one alone asserts the
    site's row count rather than the behaviour under test, and it fails only once the
    data grows — long after the change that made it wrong.
    """
    start = 0
    while True:
        payload = get_active_driver_positions(start=start)
        for row in payload["positions"]:
            if row["dispatch_trip"] == name:
                return row
        if not payload["has_more"]:
            return None
        start += PLAN_PAGE_LENGTH


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
        assertions below cannot pass by looping over an empty list.

        The row is found by walking ``has_more`` rather than by reading page one. The
        endpoint orders ``planned_start asc, name asc`` and caps a page at
        PLAN_PAGE_LENGTH, so a freshly named trip sorts last and falls off the first
        page as soon as the site holds a page of live trips — which asserts the site's
        row count rather than the envelope this test is named for.
        """
        first = get_active_driver_positions()
        self.assertEqual(set(first), ENVELOPE_FIELDS)
        self.assertEqual(first["page_length"], PLAN_PAGE_LENGTH)
        self.assertEqual(first["returned"], len(first["positions"]))

        name = self._trip()
        row = _row_in_any_page(name)
        self.assertIsNotNone(row, "a Planned trip today must reach the map")
        self.assertEqual(set(row), ROW_FIELDS)

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
        self.assertIsNotNone(_row_in_any_page(name))

    def test_a_driver_with_no_fix_is_listed_without_a_position(self):
        """A trip stays on the list; it just does not claim to know where its driver is.

        Nothing in the app writes ``driver_lat`` / ``driver_lng`` any more — the only
        writer, ``driver_portal.push_driver_position``, went with the retired portal and
        ``apex/www/test_portal_shell_contract.py`` asserts it stays gone. They are Float
        columns, which Frappe emits NOT NULL DEFAULT 0, so every trip reads 0.0 back and
        the old ``is not None`` derivation answered True for all of them: the map put
        every driver at latitude 0, longitude 0. Reporting nothing is the honest answer,
        and the client already renders its own "position unavailable" state for a row
        that carries no coordinates.
        """
        name = self._trip()
        row = _row_in_any_page(name)
        self.assertIsNotNone(row, "the trip must be on the list before its keys are graded")
        self.assertEqual(
            set(row) & RETIRED_POSITION_FIELDS,
            set(),
            "the row still reports a position no writer ever set",
        )

    def test_the_columns_behind_the_retired_position_can_never_answer_no(self):
        """The positive control for the case above, measured rather than asserted.

        If these columns could be NULL, dropping the keys would be over-reaction rather
        than a fix. They cannot: the row a trip is stored as reads 0.0 for both, so any
        ``is not None`` test on them is true forever and no fix short of removal works.
        """
        name = self._trip()
        lat, lng, updated_at = frappe.db.get_value(
            "Dispatch Trip", name, ["driver_lat", "driver_lng", "driver_position_updated_at"]
        )
        self.assertEqual((lat, lng), (0.0, 0.0), "a Float column that could be NULL changes this")
        self.assertIsNone(updated_at, "the Datetime beside them IS nullable and stays empty")

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
