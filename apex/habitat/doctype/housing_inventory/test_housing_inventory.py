# Copyright (c) 2026, afmcoltd
"""Housing Inventory: what it refuses to be created without, that picking a room fills the building
in for you, that the variance is derived rather than typed, and that a completed maintenance work
order advances the item's maintenance stamps.

The building and the rooms come from ``test_records.json``, so the links are really checked. The
previous form of this file pointed at a building named ``QA-BLDG`` that has never existed on any
site and passed ``ignore_links=True`` to stop Frappe noticing, minted its own building and room for
the fetch case, and carried a nine-line ``test_ignore`` block for masters it does not link to.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.habitat.doctype.housing_inventory.housing_inventory import reflect_completed_maintenance

test_dependencies = ["Room"]

BUILDING = "_Test Building"
ROOM = "_T-101"


class TestHousingInventory(FrappeTestCase):
    def _item(self, **overrides):
        payload = {
            "doctype": "Housing Inventory",
            "naming_series": "HINV-.YYYY.-.#####",
            "item_name": "Bunk Bed",
            "item_category": "Furniture",
            "building": BUILDING,
        }
        payload.update(overrides)
        return frappe.get_doc(payload)

    def test_an_item_takes_the_name_it_is_given(self):
        item = self._item()
        item.insert(ignore_permissions=True)
        self.addCleanup(
            frappe.delete_doc, "Housing Inventory", item.name, force=True, ignore_permissions=True
        )

        self.assertEqual(item.item_name, "Bunk Bed")
        self.assertEqual(item.building, BUILDING)

    def test_an_item_without_a_name_is_refused(self):
        item = self._item(item_name=None)

        with self.assertRaises(frappe.exceptions.MandatoryError):
            item.insert(ignore_permissions=True)

    def test_choosing_a_room_fills_in_its_building(self):
        """RED before the fix: fetch_from(room.building) sat on the room field, so picking a room
        wrote the Building docname back into the room Link (invalid) and building never
        auto-filled. GREEN: fetch_from is on building, so selecting a room populates building while
        the room field keeps a valid Room link."""
        item = self._item(item_name="Wardrobe", building=None, room=ROOM)
        item.insert(ignore_permissions=True)
        self.addCleanup(
            frappe.delete_doc, "Housing Inventory", item.name, force=True, ignore_permissions=True
        )

        self.assertEqual(item.building, BUILDING)
        self.assertEqual(item.room, ROOM)
        self.assertTrue(frappe.db.exists("Room", item.room))

    def test_the_variance_is_derived_on_save_not_typed(self):
        item = self._item(
            item_name="Pillow", item_category="Bedding & Linen",
            expected_quantity=10, counted_quantity=7,
        )
        item.insert(ignore_permissions=True)
        self.addCleanup(
            frappe.delete_doc, "Housing Inventory", item.name, force=True, ignore_permissions=True
        )

        self.assertEqual(item.quantity_variance, -3)


class TestHousingInventoryMaintenanceReflection(FrappeTestCase):
    """A completed Maintenance Work Order for a linked Facility Asset advances the housing item's
    maintenance stamps and clears a maintenance condition and status."""

    def setUp(self):
        # FrappeTestCase rolls the database back once per CLASS, not once per method —
        # frappe/tests/utils.py:46 registers _rollback_db with addClassCleanup — so the stamps one
        # case writes onto the item would still be there when the next case asserts they are not.
        frappe.db.savepoint("apex_housing_inventory_case")
        self.addCleanup(frappe.db.rollback, save_point="apex_housing_inventory_case")

        tag = frappe.generate_hash(length=12).upper()
        self.asset = frappe.get_doc({
            "doctype": "Facility Asset",
            "naming_series": "FAC-AST-.YYYY.-.####",
            "asset_name": "AC " + tag,
            "asset_category": "Other",
            "building": BUILDING,
            "responsible_supervisor": "Administrator",
        }).insert(ignore_permissions=True).name
        self.item = frappe.get_doc({
            "doctype": "Housing Inventory",
            "naming_series": "HINV-.YYYY.-.#####",
            "item_name": "AC Unit " + tag,
            "item_category": "Appliance",
            "building": BUILDING,
            "facility_asset": self.asset,
            "condition": "Needs Maintenance",
            "status": "Under Maintenance",
        }).insert(ignore_permissions=True).name

    def _completed_work_order(self, end_date):
        request = frappe.get_doc({
            "doctype": "Maintenance Request",
            "naming_series": "MAINT-.YYYY.-.#####",
            "building": BUILDING,
            "room": ROOM,
            "issue_type": "Air Conditioning",
            "reported_by": "Administrator",
            "issue_description": "AC fault",
            "related_facility_asset": self.asset,
        }).insert(ignore_permissions=True)
        return frappe.get_doc({
            "doctype": "Maintenance Work Order",
            "naming_series": "MWO-.YYYY.-.####",
            "maintenance_request": request.name,
            "planned_start_date": end_date,
            "work_description": "repair",
            "status": "Completed",
            "actual_end_date": end_date,
        })

    def _row(self):
        return frappe.get_doc("Housing Inventory", self.item)

    def test_a_completed_work_order_stamps_the_item_and_clears_its_condition(self):
        reflect_completed_maintenance(self._completed_work_order("2026-06-20"))

        row = self._row()
        self.assertEqual(str(row.last_maintenance_date), "2026-06-20")
        self.assertEqual(row.maintenance_count, 1)
        self.assertEqual(row.condition, "Good")
        self.assertEqual(row.status, "Active")

    def test_an_older_completion_does_not_roll_the_stamp_back(self):
        reflect_completed_maintenance(self._completed_work_order("2026-06-20"))
        reflect_completed_maintenance(self._completed_work_order("2026-06-01"))

        row = self._row()
        self.assertEqual(str(row.last_maintenance_date), "2026-06-20")
        self.assertEqual(row.maintenance_count, 1)

    def test_a_work_order_that_is_not_complete_changes_nothing(self):
        work_order = self._completed_work_order("2026-06-20")
        work_order.status = "In Progress"

        reflect_completed_maintenance(work_order)

        self.assertIsNone(self._row().last_maintenance_date)
