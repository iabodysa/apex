# Copyright (c) 2026, afmcoltd
"""Room Bed Transfer's own contract: it needs an assignment and a date, it refuses a target room
that carries no building, and cancelling it puts the resident back where he started.

The building, its rooms, its beds and the employee all come from ``test_records.json``. The one
record still built per case is the roomless room the integrity guard exists to reject — that is the
subject, not scaffolding. The previous form of this file rebuilt a Company, a Site, a Building, a
Room, a Bed, an Employee, a Project and an Assignment for every one of its five methods.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

# Project is deliberately NOT a dependency. ERPNext's Project fixture is not idempotent — its
# autoname mints a new name while project_name carries a unique index, so a second build attempt
# collides instead of being skipped.
test_dependencies = ["Bed", "Employee"]

BUILDING = "_Test Building"
ROOM = "_T-101"
ORIGIN_BED = "_T-101-A"
TARGET_BED = "_T-101-B"


class TestRoomBedTransfer(FrappeTestCase):
    def setUp(self):
        # FrappeTestCase rolls the database back once per CLASS, not once per method —
        # frappe/tests/utils.py:46 registers _rollback_db with addClassCleanup — so the bed one
        # case houses a resident in would still be occupied when the next case tries. A savepoint
        # is the framework's own way to hand the fixture beds back.
        frappe.db.savepoint("apex_room_bed_transfer_case")
        self.addCleanup(frappe.db.rollback, save_point="apex_room_bed_transfer_case")

        self.assignment = frappe.get_doc({
            "doctype": "Housing Assignment",
            "naming_series": "ACC-ASGN-.YYYY.-.####",
            "employee": frappe.db.get_value("Employee", {"first_name": "_Test Employee"}),
            "project": frappe.db.get_value("Project", {"project_name": "_Test Project"}),
            "building": BUILDING,
            "room": ROOM,
            "bed": ORIGIN_BED,
            "cost_center": frappe.db.get_value("Building", BUILDING, "default_cost_center"),
            "check_in_date": "2026-06-01",
            "assignment_type": "New Assignment",
        })
        self.assignment.insert(ignore_permissions=True)

    def _transfer(self, **overrides):
        payload = {
            "doctype": "Room Bed Transfer",
            "naming_series": "RBT-.YYYY.-.####",
            "assignment": self.assignment.name,
            "to_room": ROOM,
            "to_bed": TARGET_BED,
            "transfer_date": "2026-06-02",
        }
        payload.update(overrides)
        return frappe.get_doc(payload)

    def test_a_transfer_takes_the_assignment_and_target_it_is_given(self):
        transfer = self._transfer()
        transfer.insert(ignore_permissions=True)

        self.assertEqual(transfer.assignment, self.assignment.name)
        self.assertEqual(transfer.to_bed, TARGET_BED)

    def test_a_transfer_without_an_assignment_is_refused(self):
        transfer = self._transfer(assignment=None)

        with self.assertRaises(frappe.exceptions.MandatoryError):
            transfer.insert(ignore_permissions=True)

    def test_a_transfer_without_a_date_is_refused(self):
        transfer = self._transfer(transfer_date=None)

        with self.assertRaises(frappe.exceptions.MandatoryError):
            transfer.insert(ignore_permissions=True)

    def test_a_target_room_that_carries_no_building_is_refused(self):
        """The building-integrity guard: a transfer whose target room carries no building must be
        rejected in validate(). The room is minted with ignore_mandatory and the field cleared to
        be certain, and its bed is Available and belongs to the room, so every earlier gate passes
        and execution reaches the building guard."""
        tag = frappe.generate_hash(length=12).upper()
        roomless = frappe.get_doc({
            "doctype": "Room", "naming_series": "ROOM-.####",
            "room_number": "NB" + tag, "bed_capacity": 1, "readiness_status": "Ready",
        }).insert(ignore_permissions=True, ignore_mandatory=True).name
        frappe.db.set_value("Room", roomless, "building", None, update_modified=False)
        stray_bed = frappe.get_doc({
            "doctype": "Bed", "naming_series": "BED-.####", "room": roomless,
            "bed_code": "NB" + tag, "status": "Available",
        }).insert(ignore_permissions=True, ignore_mandatory=True).name

        with self.assertRaises(frappe.ValidationError):
            self._transfer(to_room=roomless, to_bed=stray_bed).insert(ignore_permissions=True)

    def test_cancelling_a_transfer_puts_the_resident_back_on_the_origin_bed(self):
        self.assignment.submit()
        transfer = self._transfer()
        transfer.insert(ignore_permissions=True)
        transfer.submit()

        self.assignment.reload()
        self.assertEqual(self.assignment.bed, TARGET_BED, "submit moves the assignment onto the target bed")
        self.assertEqual(frappe.db.get_value("Bed", TARGET_BED, "status"), "Occupied")
        self.assertEqual(frappe.db.get_value("Bed", ORIGIN_BED, "status"), "Available")

        transfer.cancel()

        self.assignment.reload()
        self.assertEqual(self.assignment.bed, ORIGIN_BED, "cancel restores the origin bed")
        self.assertEqual(self.assignment.room, ROOM, "cancel restores the origin room")
        self.assertEqual(self.assignment.building, BUILDING, "cancel restores the origin building")
        self.assertEqual(frappe.db.get_value("Bed", ORIGIN_BED, "status"), "Occupied")
        self.assertEqual(frappe.db.get_value("Bed", TARGET_BED, "status"), "Available")
