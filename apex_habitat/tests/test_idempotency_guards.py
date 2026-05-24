# Copyright (c) 2026, AFMCO and contributors
# For license information, please see license.txt
"""Reproduction tests for duplicate-record / idempotency guards.

Covers two reported scenarios:
  1. Running the Room & Bed generator wizard twice must NOT create duplicates.
  2. A second checkout for an already-checked-out assignment must be rejected.
"""

import frappe
from apex_habitat.tests.test_utils import ApexHabitatTestCase
from apex_habitat.habitat.doctype.accommodation_building.accommodation_building import (
    generate_rooms_and_beds,
)


class TestIdempotencyGuards(ApexHabitatTestCase):
    def setUp(self):
        self.company = frappe.db.get_value("Company", {}) or frappe.get_doc({
            "doctype": "Company", "company_name": "Test Company",
            "default_currency": "SAR", "country": "Saudi Arabia",
        }).insert(ignore_permissions=True).name
        self.cost_center = (
            frappe.db.get_value("Cost Center", {"is_group": 0, "company": self.company})
            or frappe.db.get_value("Cost Center", {"is_group": 0})
        )
        self.project = frappe.db.get_value("Project", {}) or frappe.get_doc({
            "doctype": "Project", "project_name": "Test Project", "company": self.company,
        }).insert(ignore_permissions=True).name
        self.employee = frappe.db.get_value("Employee", {}) or frappe.get_doc({
            "doctype": "Employee", "first_name": "Test Emp",
            "company": self.company, "gender": "Male",
            "date_of_birth": "1990-01-01", "date_of_joining": "2020-01-01",
        }).insert(ignore_permissions=True).name

        self.site = frappe.get_doc({
            "doctype": "Accommodation Site", "site_name": frappe.generate_hash(length=6),
        }).insert(ignore_permissions=True)

    def _make_building(self, abbr):
        b = frappe.get_doc({
            "doctype": "Accommodation Building",
            "building_name": f"Bldg {abbr}",
            "abbreviation": abbr,
            "site": self.site.name,
            "total_capacity": 50,
            "default_cost_center": self.cost_center,
        })
        b.append("floor_plan", {
            "floor_number": 1,
            "starting_room_number": 1,
            "room_count": 3,
            "bed_capacity_per_room": 2,
            "room_type": "Standard",
            "generate_beds": 1,
        })
        b.insert(ignore_permissions=True)
        return b

    # --- Bug 1: room generator must be idempotent ---------------------------
    def test_room_generator_run_twice_creates_no_duplicates(self):
        abbr = "T" + frappe.generate_hash(length=3).upper()
        building = self._make_building(abbr)

        first = generate_rooms_and_beds(building.name)
        rooms_after_first = frappe.db.count("Accommodation Room", {"building": building.name})
        beds_after_first = frappe.db.count(
            "Accommodation Bed", {"room": ["in", frappe.get_all(
                "Accommodation Room", {"building": building.name}, pluck="name")]}
        )

        # Run the wizard a SECOND time with the same floor plan
        second = generate_rooms_and_beds(building.name)
        rooms_after_second = frappe.db.count("Accommodation Room", {"building": building.name})
        beds_after_second = frappe.db.count(
            "Accommodation Bed", {"room": ["in", frappe.get_all(
                "Accommodation Room", {"building": building.name}, pluck="name")]}
        )

        self.assertEqual(first["created_rooms"], 3)
        self.assertEqual(
            second["created_rooms"], 0,
            "Second run must create 0 rooms (all already exist).",
        )
        self.assertEqual(second["skipped_rooms"], 3)
        self.assertEqual(
            rooms_after_second, rooms_after_first,
            f"Room count changed on re-run ({rooms_after_first} -> {rooms_after_second}): duplicates created.",
        )
        self.assertEqual(
            beds_after_second, beds_after_first,
            f"Bed count changed on re-run ({beds_after_first} -> {beds_after_second}): duplicate beds created.",
        )

    # --- Bug 2: double checkout must be rejected ----------------------------
    def _assignment(self, building, room, bed):
        a = frappe.get_doc({
            "doctype": "Accommodation Assignment",
            "employee": self.employee, "project": self.project,
            "cost_center": self.cost_center, "building": building,
            "room": room, "bed": bed, "check_in_date": "2026-05-01",
            "assignment_type": "New Assignment",
        })
        a.insert(ignore_permissions=True)
        a.submit()
        return a

    def test_second_checkout_for_same_assignment_is_rejected(self):
        abbr = "C" + frappe.generate_hash(length=3).upper()
        building = self._make_building(abbr)
        generate_rooms_and_beds(building.name)
        room = frappe.get_all("Accommodation Room", {"building": building.name}, pluck="name")[0]
        bed = frappe.get_all("Accommodation Bed", {"room": room}, pluck="name")[0]

        assignment = self._assignment(building.name, room, bed)

        checkout1 = frappe.get_doc({
            "doctype": "Accommodation Checkout", "assignment": assignment.name,
            "checkout_date": "2026-05-21", "checkout_reason": "Internal Transfer",
        })
        checkout1.insert(ignore_permissions=True)
        checkout1.submit()

        # Attempt a SECOND checkout for the same assignment — must be rejected.
        checkout2 = frappe.get_doc({
            "doctype": "Accommodation Checkout", "assignment": assignment.name,
            "checkout_date": "2026-05-22", "checkout_reason": "Internal Transfer",
        })
        with self.assertRaises(frappe.ValidationError,
                               msg="A second checkout for the same assignment must be rejected."):
            checkout2.insert(ignore_permissions=True)
            checkout2.submit()
