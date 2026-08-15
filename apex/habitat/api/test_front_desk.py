# Copyright (c) 2026, AFMCO and contributors
"""v0.8.6 — Front Desk board API: get_building_grid colours beds (green when
available + room ready) and quick_check_in creates+submits a real Accommodation
Assignment through the existing controller (bed turns red/occupied)."""

from unittest.mock import patch

import frappe
from apex.tests.factories import ApexHabitatTestCase
from apex.habitat import permissions as P
from apex.habitat.api.front_desk import (
    get_building_grid,
    get_buildings_scope_state,
    list_supervisor_buildings,
    quick_check_in,
    set_room_readiness,
)


def _h(n=12):
    return frappe.generate_hash(length=n).upper()


def _find_bed(grid, bed):
    for fl in grid["floors"]:
        for room in fl["rooms"]:
            for b in room["beds"]:
                if b["bed"] == bed:
                    return b
    return None


def _make_building(company, cc, status="Active"):
    site = frappe.get_doc({"doctype": "Site", "site_name": _h(12)}).insert(ignore_permissions=True)
    return frappe.get_doc({"doctype": "Building", "building_name": "B " + _h(),
                           "site": site.name, "total_capacity": 4, "company": company,
                           "status": status, "default_cost_center": cc}).insert(ignore_permissions=True).name


def _make_bed(building, status="Available", readiness="Ready"):
    room = frappe.get_doc({"doctype": "Room", "naming_series": "ROOM-.####",
                           "building": building, "room_number": "R" + _h(),
                           "bed_capacity": 2, "readiness_status": readiness}).insert(ignore_permissions=True).name
    return frappe.get_doc({"doctype": "Bed", "naming_series": "BED-.####",
                           "room": room, "building": building, "bed_code": "B" + _h(),
                           "status": status}).insert(ignore_permissions=True).name


class TestSupervisorBuildings(ApexHabitatTestCase):
    """T-448: list_supervisor_buildings — scope contract + server-computed bed mix."""

    def setUp(self):
        self.company = frappe.db.get_value("Company", {}) or frappe.get_doc({
            "doctype": "Company", "company_name": "Test Co", "default_currency": "SAR",
            "country": "Saudi Arabia"}).insert(ignore_permissions=True).name
        self.cc = frappe.db.get_value("Cost Center", {"is_group": 0, "company": self.company}) or frappe.db.get_value("Cost Center", {"is_group": 0})
        self.b_a = _make_building(self.company, self.cc)
        _make_bed(self.b_a, status="Available", readiness="Ready")
        _make_bed(self.b_a, status="Occupied", readiness="Ready")
        self.b_b = _make_building(self.company, self.cc)
        _make_bed(self.b_b, status="Available", readiness="Needs Cleaning")

    def _row(self, rows, building):
        return next((r for r in rows if r["building"] == building), None)

    def test_unscoped_user_sees_all_buildings_with_correct_mix(self):
        with patch.object(P, "_building_is_unscoped", return_value=True):
            rows = list_supervisor_buildings()
        names = {r["building"] for r in rows}
        self.assertIn(self.b_a, names)
        self.assertIn(self.b_b, names)

        a = self._row(rows, self.b_a)
        self.assertEqual(a["total_beds"], 2)
        self.assertEqual(a["available"], 1)
        self.assertEqual(a["occupied"], 1)
        self.assertEqual(a["blocked"], 0)
        self.assertEqual(a["occupancy_pct"], 50)

        b = self._row(rows, self.b_b)
        self.assertEqual(b["blocked"], 1, "available bed in a not-ready room counts as blocked")
        self.assertEqual(b["occupied"], 0)
        self.assertEqual(b["occupancy_pct"], 0)
        self.assertFalse(a["auto"], "multi-building scope does not auto-open")

    def test_one_building_scoped_user_sees_exactly_that_one(self):
        with patch.object(P, "_building_is_unscoped", return_value=False), patch.object(
            P, "_allowed_buildings", return_value=[self.b_a]
        ):
            rows = list_supervisor_buildings()
        self.assertEqual([r["building"] for r in rows], [self.b_a])
        self.assertEqual(rows[0]["total_beds"], 2)
        self.assertTrue(rows[0]["auto"], "one-building supervisor gets auto:true")

    def test_zero_building_scoped_user_sees_empty(self):
        with patch.object(P, "_building_is_unscoped", return_value=False), patch.object(
            P, "_allowed_buildings", return_value=[]
        ):
            self.assertEqual(list_supervisor_buildings(), [])

    def test_rows_are_grouped_by_site_then_sorted_by_title(self):
        """Site is the PRIMARY sort key (front_desk.py:371), so the building titles are
        only sorted WITHIN a site — a flat ``titles == sorted(titles)`` graded an order
        the endpoint has never produced whenever the caller's estate spans two sites."""
        with patch.object(P, "_building_is_unscoped", return_value=True):
            rows = list_supervisor_buildings()
        keys = [(str(r["site_title"] or ""), str(r["building_title"])) for r in rows]
        self.assertEqual(keys, sorted(keys))
        self.assertGreaterEqual(len(rows), 2, "the order was graded over fewer than two rows")

    def test_scope_state_flags_permission_gap_for_scoped_user_with_none(self):
        with patch.object(P, "_building_is_unscoped", return_value=False), patch.object(
            P, "_allowed_buildings", return_value=[]
        ):
            state = get_buildings_scope_state()
        self.assertTrue(state["is_scoped"])
        self.assertEqual(state["active_buildings"], 0)

    def test_scope_state_unscoped_user_is_not_a_permission_gap(self):
        with patch.object(P, "_building_is_unscoped", return_value=True):
            state = get_buildings_scope_state()
        self.assertFalse(state["is_scoped"])
        self.assertGreaterEqual(state["active_buildings"], 2)


class TestSetRoomReadiness(ApexHabitatTestCase):
    """T-453: set_room_readiness flips Accommodation Room.readiness_status, the
    board reflects it, and a read-only role is refused the write."""

    def setUp(self):
        frappe.set_user("Administrator")
        self.company = frappe.db.get_value("Company", {}) or frappe.get_doc({
            "doctype": "Company", "company_name": "Test Co", "default_currency": "SAR",
            "country": "Saudi Arabia"}).insert(ignore_permissions=True).name
        self.cc = frappe.db.get_value("Cost Center", {"is_group": 0, "company": self.company}) or frappe.db.get_value("Cost Center", {"is_group": 0})
        self.building = _make_building(self.company, self.cc)
        self.room = frappe.get_doc({"doctype": "Room", "naming_series": "ROOM-.####",
                                    "building": self.building, "room_number": "R" + _h(),
                                    "bed_capacity": 2, "readiness_status": "Needs Cleaning"}).insert(ignore_permissions=True).name
        self.bed = frappe.get_doc({"doctype": "Bed", "naming_series": "BED-.####",
                                   "room": self.room, "building": self.building, "bed_code": "B" + _h(),
                                   "status": "Available"}).insert(ignore_permissions=True).name

    def tearDown(self):
        frappe.set_user("Administrator")

    def _user_with_roles(self, email, roles):
        if not frappe.db.exists("User", email):
            frappe.get_doc({
                "doctype": "User", "email": email, "first_name": email.split("@")[0],
                "roles": [{"role": r} for r in roles],
            }).insert(ignore_permissions=True)
        return email

    def test_flip_to_ready_turns_bed_green_on_board(self):
        b = _find_bed(get_building_grid(self.building), self.bed)
        self.assertEqual(b["bed_color"], "amber")

        out = set_room_readiness(room=self.room, status="Ready")
        self.assertEqual(out["readiness_status"], "Ready")
        self.assertEqual(frappe.db.get_value("Room", self.room, "readiness_status"), "Ready")

        b2 = _find_bed(get_building_grid(self.building), self.bed)
        self.assertEqual(b2["bed_color"], "green", "board reflects the readiness flip")

    def test_invalid_status_is_rejected(self):
        with self.assertRaises(frappe.ValidationError):
            set_room_readiness(room=self.room, status="Sparkling")

    def test_read_only_role_is_refused(self):
        frappe.set_user(self._user_with_roles("fd-readiness-ro@test.local", ["Resident Supervisor"]))
        try:
            with self.assertRaises(frappe.PermissionError):
                set_room_readiness(room=self.room, status="Ready")
        finally:
            frappe.set_user("Administrator")
