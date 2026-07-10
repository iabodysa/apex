# Copyright (c) 2026, AFMCO and contributors
import frappe
from frappe.tests.utils import FrappeTestCase

test_ignore = [
    "Asset",
    "Company",
    "Cost Center",
    "Currency",
    "Employee",
    "Item",
    "Role",
    "User",
]


class TestHousingInventory(FrappeTestCase):

    def test_create_valid_item(self):
        doc = frappe.get_doc({
            "doctype": "Housing Inventory",
            "naming_series": "HINV-.YYYY.-.#####",
            "item_name": "Bunk Bed",
            "item_category": "Furniture",
            "building": "QA-BLDG",
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.assertIsNotNone(doc.name)
        frappe.delete_doc("Housing Inventory", doc.name, force=True, ignore_permissions=True)

    def test_missing_item_name_raises(self):
        doc = frappe.get_doc({
            "doctype": "Housing Inventory",
            "naming_series": "HINV-.YYYY.-.#####",
            "item_category": "Furniture",
            "building": "QA-BLDG",
        })
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert(ignore_permissions=True, ignore_links=True)

    def test_building_fetches_from_chosen_room(self):
        """RED before fix: fetch_from(room.building) sat on the room field, so picking a
        room wrote the Building docname back into the room Link (invalid) and building
        never auto-filled. GREEN: fetch_from is on building, so selecting a room
        populates building while the room field keeps a valid Room link."""
        h = frappe.generate_hash(length=6)
        building = frappe.get_doc({
            "doctype": "Building", "building_name": "HI Bldg " + h,
        }).insert(ignore_permissions=True, ignore_links=True).name
        room = frappe.get_doc({
            "doctype": "Room", "room_number": "HIR" + h, "building": building,
        }).insert(ignore_permissions=True, ignore_links=True).name
        doc = frappe.get_doc({
            "doctype": "Housing Inventory",
            "naming_series": "HINV-.YYYY.-.#####",
            "item_name": "Wardrobe",
            "item_category": "Furniture",
            "room": room,  # building left blank — must fetch from the room
        })
        doc.insert(ignore_permissions=True)
        self.assertEqual(doc.building, building)
        # The room field stays a valid Accommodation Room link, not a Building docname.
        self.assertEqual(doc.room, room)
        self.assertTrue(frappe.db.exists("Room", doc.room))
        frappe.delete_doc("Housing Inventory", doc.name, force=True, ignore_permissions=True)

    def test_variance_is_derived_on_save(self):
        doc = frappe.get_doc({
            "doctype": "Housing Inventory",
            "naming_series": "HINV-.YYYY.-.#####",
            "item_name": "Pillow",
            "item_category": "Bedding & Linen",
            "building": "QA-BLDG",
            "expected_quantity": 10,
            "counted_quantity": 7,
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.assertEqual(doc.quantity_variance, -3)
        frappe.delete_doc("Housing Inventory", doc.name, force=True, ignore_permissions=True)


class TestHousingInventoryMaintenanceReflection(FrappeTestCase):
    """A completed Maintenance Work Order for a linked Facility Asset advances the
    housing item's maintenance stamps and clears a maintenance condition/status."""

    def _h(self):
        return frappe.generate_hash(length=6).upper()

    def setUp(self):
        self.company = frappe.db.get_value("Company", {}) or frappe.get_doc({
            "doctype": "Company", "company_name": "Test Co", "default_currency": "SAR",
            "country": "Saudi Arabia"}).insert(ignore_permissions=True).name
        self.building = frappe.get_doc({
            "doctype": "Building", "building_name": "B " + self._h(),
            "total_capacity": 4, "company": self.company,
        }).insert(ignore_permissions=True, ignore_links=True).name
        self.asset = frappe.get_doc({
            "doctype": "Facility Asset", "naming_series": "FAC-AST-.YYYY.-.####",
            "asset_name": "AC " + self._h(), "asset_category": "Other",
            "building": self.building, "responsible_supervisor": "Administrator",
        }).insert(ignore_permissions=True, ignore_links=True).name
        self.item = frappe.get_doc({
            "doctype": "Housing Inventory", "naming_series": "HINV-.YYYY.-.#####",
            "item_name": "AC Unit " + self._h(), "item_category": "Appliance",
            "building": self.building, "facility_asset": self.asset,
            "condition": "Needs Maintenance", "status": "Under Maintenance",
        }).insert(ignore_permissions=True).name

    def _completed_work_order(self, end_date):
        # Minimal completed Work Order whose request points at the linked asset.
        mr = frappe.get_doc({
            "doctype": "Maintenance Request", "naming_series": "MAINT-.YYYY.-.#####",
            "building": self.building, "room": self._room(), "issue_type": "Air Conditioning",
            "reported_by": "Administrator", "issue_description": "AC fault",
            "related_facility_asset": self.asset,
        }).insert(ignore_permissions=True, ignore_links=True)
        return frappe.get_doc({
            "doctype": "Maintenance Work Order", "naming_series": "MWO-.YYYY.-.####",
            "maintenance_request": mr.name, "planned_start_date": end_date,
            "work_description": "repair", "status": "Completed", "actual_end_date": end_date,
        })

    def _room(self):
        return frappe.get_doc({
            "doctype": "Room", "room_number": "R" + self._h(),
            "building": self.building,
        }).insert(ignore_permissions=True, ignore_links=True).name

    def _item(self):
        return frappe.get_doc("Housing Inventory", self.item)

    def test_completed_maintenance_reflects(self):
        from apex_habitat.habitat.doctype.housing_inventory.housing_inventory import (
            reflect_completed_maintenance,
        )

        wo = self._completed_work_order("2026-06-20")
        reflect_completed_maintenance(wo)
        row = self._item()
        self.assertEqual(str(row.last_maintenance_date), "2026-06-20")
        self.assertEqual(row.maintenance_count, 1)
        self.assertEqual(row.condition, "Good")
        self.assertEqual(row.status, "Active")

    def test_older_completion_does_not_roll_back(self):
        from apex_habitat.habitat.doctype.housing_inventory.housing_inventory import (
            reflect_completed_maintenance,
        )

        reflect_completed_maintenance(self._completed_work_order("2026-06-20"))
        reflect_completed_maintenance(self._completed_work_order("2026-06-01"))
        row = self._item()
        self.assertEqual(str(row.last_maintenance_date), "2026-06-20")
        self.assertEqual(row.maintenance_count, 1)

    def test_non_completed_is_noop(self):
        from apex_habitat.habitat.doctype.housing_inventory.housing_inventory import (
            reflect_completed_maintenance,
        )

        wo = self._completed_work_order("2026-06-20")
        wo.status = "In Progress"
        reflect_completed_maintenance(wo)
        self.assertIsNone(self._item().last_maintenance_date)
