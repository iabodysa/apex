# Copyright (c) 2026, AFMCO and contributors
"""v0.8.6 — Front Desk board API: get_building_grid colours beds (green when
available + room ready) and quick_check_in creates+submits a real Accommodation
Assignment through the existing controller (bed turns red/occupied)."""

import frappe
from apex_habitat.tests.test_utils import ApexHabitatTestCase
from apex_habitat.habitat.api.front_desk import get_building_grid, quick_check_in


def _h(n=4):
    return frappe.generate_hash(length=n).upper()


def _find_bed(grid, bed):
    for fl in grid["floors"]:
        for room in fl["rooms"]:
            for b in room["beds"]:
                if b["bed"] == bed:
                    return b
    return None


class TestFrontDesk(ApexHabitatTestCase):
    def setUp(self):
        self.company = frappe.db.get_value("Company", {}) or frappe.get_doc({
            "doctype": "Company", "company_name": "Test Co", "default_currency": "SAR",
            "country": "Saudi Arabia"}).insert(ignore_permissions=True).name
        self.cc = frappe.db.get_value("Cost Center", {"is_group": 0, "company": self.company}) or frappe.db.get_value("Cost Center", {"is_group": 0})
        self.site = frappe.get_doc({"doctype": "Accommodation Site", "site_name": _h(6)}).insert(ignore_permissions=True)
        self.building = frappe.get_doc({"doctype": "Accommodation Building", "building_name": "B " + _h(),
                                        "site": self.site.name, "total_capacity": 4, "company": self.company,
                                        "default_cost_center": self.cc}).insert(ignore_permissions=True).name
        self.room = frappe.get_doc({"doctype": "Accommodation Room", "naming_series": "ROOM-.####",
                                    "building": self.building, "room_number": "R" + _h(),
                                    "bed_capacity": 2, "readiness_status": "Ready"}).insert(ignore_permissions=True).name
        self.bed = frappe.get_doc({"doctype": "Accommodation Bed", "naming_series": "BED-.####",
                                   "room": self.room, "building": self.building, "bed_code": "B" + _h(),
                                   "status": "Available"}).insert(ignore_permissions=True).name
        self.employee = frappe.get_doc({"doctype": "Employee", "first_name": "E " + _h(), "company": self.company,
                                        "gender": "Male", "date_of_birth": "1990-01-01", "date_of_joining": "2020-01-01"}).insert(ignore_permissions=True).name
        self.project = frappe.get_doc({"doctype": "Project", "project_name": "P " + _h()}).insert(ignore_permissions=True).name

    def test_grid_shows_available_bed_green_then_red_after_checkin(self):
        grid = get_building_grid(self.building)
        b = _find_bed(grid, self.bed)
        self.assertIsNotNone(b, "bed must appear on the board")
        self.assertEqual(b["bed_color"], "green", "available bed in a ready room is green")

        quick_check_in(bed=self.bed, employee=self.employee, project=self.project,
                       check_in_date="2026-05-01", cost_center=self.cc)

        grid2 = get_building_grid(self.building)
        b2 = _find_bed(grid2, self.bed)
        self.assertEqual(b2["bed_color"], "red", "bed is red after check-in")
        self.assertTrue(b2.get("occupant"), "occupied bed carries occupant info")
        # the check-in created a submitted assignment through the real controller
        self.assertTrue(frappe.db.exists("Accommodation Assignment",
                        {"bed": self.bed, "docstatus": 1, "check_out_date": ["is", "not set"]}))

    def test_amber_when_room_not_ready(self):
        frappe.db.set_value("Accommodation Room", self.room, "readiness_status", "Needs Cleaning")
        grid = get_building_grid(self.building)
        b = _find_bed(grid, self.bed)
        self.assertEqual(b["bed_color"], "amber", "available bed in a not-ready room is amber")
