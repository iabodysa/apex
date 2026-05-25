# Copyright (c) 2026, AFMCO and contributors
"""v0.9.0 visual pages — smoke tests for the read/write APIs behind the Transfer
Board, Safety Map, and Custody Kiosk. Writes go through the real controllers."""

import json
import frappe
from apex_habitat.tests.test_utils import ApexHabitatTestCase
from apex_habitat.habitat.api.front_desk import quick_check_in
from apex_habitat.habitat.api.transfer_board import transfer_occupant
from apex_habitat.habitat.api.safety_map import get_safety_map
from apex_habitat.habitat.api.custody_kiosk import get_kiosk_catalog, issue_cart


def _h(n=4):
    return frappe.generate_hash(length=n).upper()


class TestV090Pages(ApexHabitatTestCase):
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
                                    "bed_capacity": 4, "readiness_status": "Ready"}).insert(ignore_permissions=True).name
        self.bed1 = self._bed()
        self.bed2 = self._bed()
        self.employee = frappe.get_doc({"doctype": "Employee", "first_name": "E " + _h(), "company": self.company,
                                        "gender": "Male", "date_of_birth": "1990-01-01", "date_of_joining": "2020-01-01"}).insert(ignore_permissions=True).name
        self.project = frappe.get_doc({"doctype": "Project", "project_name": "P " + _h()}).insert(ignore_permissions=True).name

    def _bed(self):
        return frappe.get_doc({"doctype": "Accommodation Bed", "naming_series": "BED-.####",
                               "room": self.room, "building": self.building, "bed_code": "B" + _h(),
                               "status": "Available"}).insert(ignore_permissions=True).name

    def test_transfer_board_moves_occupant(self):
        quick_check_in(bed=self.bed1, employee=self.employee, project=self.project,
                       check_in_date="2026-05-01", cost_center=self.cc)
        transfer_occupant(source_bed=self.bed1, target_bed=self.bed2, transfer_date="2026-05-02")
        # active assignment now sits on bed2; beds swapped status
        self.assertTrue(frappe.db.exists("Accommodation Assignment",
                        {"bed": self.bed2, "docstatus": 1, "check_out_date": ["is", "not set"]}))
        self.assertEqual(frappe.db.get_value("Accommodation Bed", self.bed1, "status"), "Available")
        self.assertEqual(frappe.db.get_value("Accommodation Bed", self.bed2, "status"), "Occupied")

    def test_safety_map_returns_floor_structure(self):
        grid = get_safety_map(self.building)
        self.assertEqual(grid["building"], self.building)
        self.assertIn("floors", grid)
        rooms = [r for fl in grid["floors"] for r in fl["rooms"]]
        self.assertTrue(any(r["room"] == self.room for r in rooms))

    def test_custody_kiosk_catalog_and_issue(self):
        cat = frappe.db.get_value("Custody Asset Category", {}) or frappe.get_doc({
            "doctype": "Custody Asset Category", "category_name": "Cat " + _h()}).insert(ignore_permissions=True).name
        article = frappe.get_doc({"doctype": "Custody Article", "naming_series": "ART-.####",
                                  "article_name": "Blanket " + _h(), "category": cat,
                                  "unit_of_measure": "Nos"}).insert(ignore_permissions=True).name
        catalog = get_kiosk_catalog(self.building)
        self.assertTrue(any(a["article"] == article for a in catalog["articles"]))

        res = issue_cart(employee=self.employee, building=self.building,
                         items_json=json.dumps([{"article": article, "qty": 2}]))
        ci = res["custody_issue"]
        self.assertEqual(frappe.db.get_value("Custody Issue", ci, "docstatus"), 1)
