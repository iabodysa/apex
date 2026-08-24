# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

test_ignore = ["Facility Asset", "Maintenance Work Order"]


class TestTheRoomOwnsTheBuilding(FrappeTestCase):
    def _row(self, **fields):
        doc = frappe.get_doc(
            {
                "doctype": "Housing Inventory",
                "item_name": "_T-Inventory-Item",
                "item_category": "Furniture",
            }
        )
        doc.update(fields)
        return doc

    def test_a_building_that_disagrees_with_the_room_is_overwritten(self):
        room_building = frappe.db.get_value("Room", "_T-101", "building")
        self.assertEqual(room_building, "_Test Building")

        doc = self._row(room="_T-101", building="_Test Building 2")
        doc.insert()
        self.addCleanup(frappe.delete_doc, "Housing Inventory", doc.name, force=True)
        self.assertEqual(doc.building, room_building)

    def test_a_blank_building_is_filled_from_the_room(self):
        doc = self._row(room="_T-101")
        doc.insert()
        self.addCleanup(frappe.delete_doc, "Housing Inventory", doc.name, force=True)
        self.assertEqual(doc.building, "_Test Building")

    def test_building_level_stock_keeps_its_own_building(self):
        doc = self._row(building="_Test Building 2")
        doc.insert()
        self.addCleanup(frappe.delete_doc, "Housing Inventory", doc.name, force=True)
        self.assertEqual(doc.building, "_Test Building 2")
