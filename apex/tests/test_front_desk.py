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
        self.site = frappe.get_doc({"doctype": "Site", "site_name": _h(6)}).insert(ignore_permissions=True)
        self.building = frappe.get_doc({"doctype": "Building", "building_name": "B " + _h(),
                                        "site": self.site.name, "total_capacity": 4, "company": self.company,
                                        "default_cost_center": self.cc}).insert(ignore_permissions=True).name
        self.room = frappe.get_doc({"doctype": "Room", "naming_series": "ROOM-.####",
                                    "building": self.building, "room_number": "R" + _h(),
                                    "bed_capacity": 2, "readiness_status": "Ready"}).insert(ignore_permissions=True).name
        self.bed = frappe.get_doc({"doctype": "Bed", "naming_series": "BED-.####",
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
        # [#4va3oo]
        self.assertTrue(frappe.db.exists("Housing Assignment",
                        {"bed": self.bed, "docstatus": 1, "check_out_date": ["is", "not set"]}))

    def test_amber_when_room_not_ready(self):
        frappe.db.set_value("Room", self.room, "readiness_status", "Needs Cleaning")
        grid = get_building_grid(self.building)
        b = _find_bed(grid, self.bed)
        self.assertEqual(b["bed_color"], "amber", "available bed in a not-ready room is amber")


def _make_building(company, cc, status="Active"):
    site = frappe.get_doc({"doctype": "Site", "site_name": _h(6)}).insert(ignore_permissions=True)
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
        # Building A: one green (available+ready) + one red (occupied) bed.
        self.b_a = _make_building(self.company, self.cc)
        _make_bed(self.b_a, status="Available", readiness="Ready")
        _make_bed(self.b_a, status="Occupied", readiness="Ready")
        # Building B: one amber (available + not-ready) bed only.
        self.b_b = _make_building(self.company, self.cc)
        _make_bed(self.b_b, status="Available", readiness="Needs Cleaning")

    def _row(self, rows, building):
        return next((r for r in rows if r["building"] == building), None)

    def test_unscoped_user_sees_all_buildings_with_correct_mix(self):
        with patch.object(P, "_building_is_unscoped", return_value=True):
            rows = list_supervisor_buildings()
        names = {r["building"] for r in rows}
        # Unscoped role sees every Active building (incl. both test buildings).
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
        # More than one building in scope: no auto-open hint (the user must pick).
        self.assertFalse(a["auto"], "multi-building scope does not auto-open")

    def test_one_building_scoped_user_sees_exactly_that_one(self):
        with patch.object(P, "_building_is_unscoped", return_value=False), patch.object(
            P, "_allowed_buildings", return_value=[self.b_a]
        ):
            rows = list_supervisor_buildings()
        self.assertEqual([r["building"] for r in rows], [self.b_a])
        self.assertEqual(rows[0]["total_beds"], 2)
        # A single allowed building carries the auto-open hint so the Front Desk
        # lands straight on a loaded board with no chip interaction.
        self.assertTrue(rows[0]["auto"], "one-building supervisor gets auto:true")

    def test_zero_building_scoped_user_sees_empty(self):
        with patch.object(P, "_building_is_unscoped", return_value=False), patch.object(
            P, "_allowed_buildings", return_value=[]
        ):
            self.assertEqual(list_supervisor_buildings(), [])

    def test_rows_sorted_by_title(self):
        with patch.object(P, "_building_is_unscoped", return_value=True):
            rows = list_supervisor_buildings()
        titles = [r["building_title"] for r in rows]
        self.assertEqual(titles, sorted(titles))

    # An empty building list has two meanings; the scope-state endpoint
    # tells them apart so the client can show the right empty copy.
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
        # The seeded test buildings are Active, so the unscoped count is positive.
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
        # Not-ready room -> the available bed is amber on the board.
        b = _find_bed(get_building_grid(self.building), self.bed)
        self.assertEqual(b["bed_color"], "amber")

        out = set_room_readiness(room=self.room, status="Ready")
        self.assertEqual(out["readiness_status"], "Ready")
        self.assertEqual(frappe.db.get_value("Room", self.room, "readiness_status"), "Ready")

        # Board now reflects the change: the same bed is green.
        b2 = _find_bed(get_building_grid(self.building), self.bed)
        self.assertEqual(b2["bed_color"], "green", "board reflects the readiness flip")

    def test_invalid_status_is_rejected(self):
        with self.assertRaises(frappe.ValidationError):
            set_room_readiness(room=self.room, status="Sparkling")

    def test_read_only_role_is_refused(self):
        # Resident Supervisor has read (not write) on Accommodation Room.
        frappe.set_user(self._user_with_roles("fd-readiness-ro@test.local", ["Resident Supervisor"]))
        try:
            with self.assertRaises(frappe.PermissionError):
                set_room_readiness(room=self.room, status="Ready")
        finally:
            frappe.set_user("Administrator")
