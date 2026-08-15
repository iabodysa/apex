# Copyright (c) 2026, afmcoltd
"""The three visual pages behind v0.9.0 — Transfer Board, Safety Map and Custody Kiosk — reached
through their real read/write APIs, so every write goes through the controller a user's tap would.

Nothing here builds a world. ``test_dependencies`` names the roots and Frappe stands the whole
chain up once per run — Bed pulls Room, Room pulls Building, Building pulls Site and Company,
Custody Article pulls its category, and Employee comes from ERPNext's own fixture. The previous
form of this file built a Company, a Site, a Building, a Room, two Beds, an Employee, a Project, a
Custody Asset Category and a Custody Article in ``setUp``, per test method.
"""

from __future__ import annotations

import json

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.habitat.api.custody_kiosk import get_kiosk_catalog, issue_cart
from apex.habitat.api.front_desk import quick_check_in
from apex.habitat.api.safety_map import get_safety_map
from apex.habitat.api.transfer_board import transfer_occupant

# Project is deliberately NOT a dependency. ERPNext's Project fixture is not idempotent — its
# autoname mints a new name while project_name carries a unique index, so a second build attempt
# collides instead of being skipped.
test_dependencies = ["Bed", "Custody Article", "Employee"]

BUILDING = "_Test Building"
ROOM = "_T-102"
SOURCE_BED = "_T-102-A"
TARGET_BED = "_T-102-B"


class TestV090Pages(FrappeTestCase):
    def setUp(self):
        # FrappeTestCase rolls the database back once per CLASS, not once per method —
        # frappe/tests/utils.py:46 registers _rollback_db with addClassCleanup — so the resident
        # the transfer case houses would still hold the fixture bed when the kiosk case runs. A
        # savepoint is the framework's own way to hand the beds and the store back.
        frappe.db.savepoint("apex_v090_pages_case")
        self.addCleanup(frappe.db.rollback, save_point="apex_v090_pages_case")

        self.cost_center = frappe.db.get_value("Building", BUILDING, "default_cost_center")
        self.employee = frappe.db.get_value("Employee", {"first_name": "_Test Employee"})
        self.project = frappe.db.get_value("Project", {"project_name": "_Test Project"})
        self.article = frappe.db.get_value("Custody Article", {"article_name": "_Test Blanket"})

    def test_the_transfer_board_moves_the_occupant_onto_the_target_bed(self):
        quick_check_in(
            bed=SOURCE_BED, employee=self.employee, project=self.project,
            check_in_date="2026-05-01", cost_center=self.cost_center,
        )

        transfer_occupant(source_bed=SOURCE_BED, target_bed=TARGET_BED, transfer_date="2026-05-02")

        self.assertTrue(frappe.db.exists("Housing Assignment", {
            "bed": TARGET_BED, "docstatus": 1, "check_out_date": ["is", "not set"],
        }))
        self.assertEqual(frappe.db.get_value("Bed", SOURCE_BED, "status"), "Available")
        self.assertEqual(frappe.db.get_value("Bed", TARGET_BED, "status"), "Occupied")

    def test_the_safety_map_returns_the_buildings_floors_and_rooms(self):
        grid = get_safety_map(BUILDING)

        self.assertEqual(grid["building"], BUILDING)
        self.assertIn("floors", grid)
        rooms = [room for floor in grid["floors"] for room in floor["rooms"]]
        self.assertTrue(any(room["room"] == ROOM for room in rooms))

    def test_the_custody_kiosk_lists_an_article_and_issues_a_cart_of_it(self):
        from apex.habitat.doctype.accommodation_stock_ledger.accommodation_stock_ledger import (
            post_stock_entry,
        )

        catalog = get_kiosk_catalog(BUILDING)
        self.assertTrue(any(a["article"] == self.article for a in catalog["articles"]))

        post_stock_entry(
            item_type="Custody Article", item=self.article, qty=2, building=BUILDING,
            voucher_type="Opening Stock", voucher_no="OPEN-" + frappe.generate_hash(length=12).upper(),
        )

        result = issue_cart(
            employee=self.employee, building=BUILDING,
            items_json=json.dumps([{"article": self.article, "qty": 2}]),
        )

        self.assertEqual(frappe.db.get_value("Custody Issue", result["custody_issue"], "docstatus"), 1)
