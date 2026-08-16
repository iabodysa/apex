# Copyright (c) 2026, afmcoltd
"""The Front Desk board: what colour a bed shows, and what a quick check-in leaves behind.

Nothing here builds a world. ``test_dependencies`` names the three roots and Frappe stands the whole
chain up once per run — Bed pulls Room, Room pulls Building, Building pulls Site and Company, and
Employee and Project come from ERPNext's own fixtures, not eight records built in ``setUp`` per
test method to assert the colour of one bed.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.habitat.api.front_desk import get_building_grid, quick_check_in

# Project is deliberately NOT a dependency. ERPNext's Project fixture is not idempotent — its
# autoname mints a new name while project_name carries a unique index, so a second build attempt
# collides instead of being skipped. The check-in only needs a project id, so the one already on
# the site is read rather than rebuilt.
test_dependencies = ["Bed", "Employee"]

BUILDING = "_Test Building"
BED = "_T-101-A"
OCCUPIABLE_BED = "_T-101-B"
ROOM = "_T-101"


def _bed_on(grid, bed):
    for floor in grid["floors"]:
        for room in floor["rooms"]:
            for row in room["beds"]:
                if row["bed"] == bed:
                    return row
    return None


class TestFrontDeskGrid(FrappeTestCase):
    def setUp(self):
        self.cost_center = frappe.db.get_value("Cost Center", {"is_group": 0})
        self.employee = frappe.db.get_value("Employee", {"first_name": "_Test Employee"})
        self.project = frappe.db.get_value("Project", {"project_name": "_Test Project"})

    def test_an_available_bed_in_a_ready_room_shows_green(self):
        row = _bed_on(get_building_grid(BUILDING), BED)

        self.assertIsNotNone(row, "the bed must appear on the board")
        self.assertEqual(row["bed_color"], "green")

    def test_a_bed_turns_red_and_carries_its_occupant_after_a_check_in(self):
        # This case takes the SECOND fixture bed, not the shared one. quick_check_in submits a
        # Housing Assignment and commits, so the change outlives the per-test rollback — a case
        # that commits must own the record it changes.
        quick_check_in(
            bed=OCCUPIABLE_BED,
            employee=self.employee,
            project=self.project,
            check_in_date="2026-05-01",
            cost_center=self.cost_center,
        )

        row = _bed_on(get_building_grid(BUILDING), OCCUPIABLE_BED)
        self.assertEqual(row["bed_color"], "red")
        self.assertTrue(row.get("occupant"), "an occupied bed carries who is in it")
        self.assertTrue(frappe.db.exists("Housing Assignment", {
            "bed": OCCUPIABLE_BED,
            "docstatus": 1,
            "check_out_date": ["is", "not set"],
        }))

    def test_a_bed_in_a_room_that_is_not_ready_shows_amber(self):
        # The room is shared with the other cases in this class, so the readiness it borrows is
        # handed back. A fixture is only reusable while every test leaves it as it found it.
        self.addCleanup(frappe.db.set_value, "Room", ROOM, "readiness_status", "Ready")
        frappe.db.set_value("Room", ROOM, "readiness_status", "Needs Cleaning")

        row = _bed_on(get_building_grid(BUILDING), BED)
        self.assertEqual(row["bed_color"], "amber")
