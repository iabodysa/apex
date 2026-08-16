# Copyright (c) 2026, afmcoltd
"""The daily occupancy snapshot: one read-only row per building per day, written once.

Nothing here builds a world. ``test_dependencies`` names the two roots and Frappe stands the whole
chain up once per run — Bed pulls Room, Room pulls Building, Building pulls Site and Company, and
Employee comes from ERPNext's own fixture, not Company, Project, Employee, Site, Building, Room and
Bed built in ``setUp`` per test method to assert four numbers on one snapshot row.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today

from apex.habitat.tasks import daily_occupancy_snapshot

# Project is deliberately NOT a dependency. ERPNext's Project fixture is not idempotent — its
# autoname mints a new name while project_name carries a unique index, so a second build attempt
# collides instead of being skipped. The assignment only needs a project id, so the one already on
# the site is read rather than rebuilt.
test_dependencies = ["Bed", "Employee"]

BUILDING = "_Test Building"
ROOM = "_T-101"
BED = "_T-101-A"


class TestOccupancySnapshot(FrappeTestCase):
    def test_one_assignment_yields_one_snapshot_row_and_a_second_run_adds_none(self):
        assignment = frappe.get_doc({
            "doctype": "Housing Assignment",
            "employee": frappe.db.get_value("Employee", {"first_name": "_Test Employee"}),
            "project": frappe.db.get_value("Project", {"project_name": "_Test Project"}),
            "cost_center": frappe.db.get_value("Cost Center", {"is_group": 0}),
            "building": BUILDING,
            "room": ROOM,
            "bed": BED,
            "check_in_date": today(),
            "assignment_type": "New Assignment",
        })
        assignment.insert(ignore_permissions=True)
        assignment.submit()

        # The job skips any building that already holds a snapshot for the date
        # (habitat/tasks/occupancy.py:158-166). A row committed by an earlier run therefore
        # makes it skip this building, and every assertion below grades that row instead of
        # the one this test asked for.
        frappe.db.delete("Occupancy Snapshot", {"building": BUILDING, "snapshot_date": today()})

        daily_occupancy_snapshot()
        rows = frappe.get_all(
            "Occupancy Snapshot",
            filters={"building": BUILDING, "snapshot_date": today()},
            fields=["active_occupants", "total_capacity", "occupancy_percent", "available_capacity"],
        )
        self.assertEqual(len(rows), 1, "expected exactly one snapshot for the building today")
        self.assertEqual(rows[0].active_occupants, 1)
        self.assertEqual(rows[0].total_capacity, 4)
        self.assertEqual(rows[0].occupancy_percent, 25.0)
        self.assertEqual(rows[0].available_capacity, 3)

        daily_occupancy_snapshot()
        self.assertEqual(
            frappe.db.count("Occupancy Snapshot", {"building": BUILDING, "snapshot_date": today()}),
            1,
            "snapshot must be idempotent per building per day",
        )

    def test_the_snapshot_engine_grants_nobody_create(self):
        meta = frappe.get_meta("Occupancy Snapshot")
        self.assertFalse(any(p.create for p in meta.permissions), "snapshot must be read-only")
