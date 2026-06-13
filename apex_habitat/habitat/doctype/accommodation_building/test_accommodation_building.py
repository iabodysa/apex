import frappe
from frappe.tests.utils import FrappeTestCase

# Prevent Frappe test runner from recursively resolving Link-field dependencies
# on external DocTypes that require ERPNext (not installed in CI bench).
test_ignore = [
    "Additional Salary",
    "Asset",
    "Asset Movement",
    "Company",
    "Cost Center",
    "Currency",
    "Employee",
    "Item",
    "Payment Entry",
    "Project",
    "Purchase Invoice",
    "Role",
    "Salary Component",
    "Supplier",
    "User",
]


class TestAccommodationBuilding(FrappeTestCase):

    def test_create_valid_building(self):
        doc = frappe.get_doc({
            "doctype": "Accommodation Building",
            "building_name": "QA Test Building",
            "total_capacity": 20,
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.assertEqual(doc.building_name, "QA Test Building")
        frappe.delete_doc("Accommodation Building", doc.name, force=True, ignore_permissions=True)

    def test_missing_building_name_raises(self):
        doc = frappe.get_doc({
            "doctype": "Accommodation Building",
            "total_capacity": 10,
        })
        with self.assertRaises(frappe.exceptions.ValidationError):
            doc.insert(ignore_permissions=True, ignore_links=True)

    def test_missing_capacity_raises(self):
        doc = frappe.get_doc({
            "doctype": "Accommodation Building",
            "building_name": "QA Missing Capacity",
        })
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert(ignore_permissions=True, ignore_links=True)

    # --- room-number prefix (Room Generator professionalization) -------------
    def test_room_number_blank_prefix_is_byte_identical(self):
        from apex_habitat.habitat.doctype.accommodation_building.accommodation_building import _room_number
        # A blank prefix must keep the historical format exactly (zero renumbering).
        self.assertEqual(_room_number("JED1", "G", "", 1), "JED1-G01")
        self.assertEqual(_room_number("JED1", "1", "", 5), "JED1-105")

    def test_room_number_with_prefix(self):
        from apex_habitat.habitat.doctype.accommodation_building.accommodation_building import _room_number
        self.assertEqual(_room_number("JED1", "G", "A", 1), "JED1-GA01")
        self.assertEqual(_room_number("JED1", "1", "B", 5), "JED1-1B05")
        self.assertEqual(_room_number("JED1", "G", " A ", 1), "JED1-GA01")  # whitespace stripped

    def test_abbreviation_locked_after_rooms_exist(self):
        # Once a room uses the building code, changing the code is blocked (it would
        # orphan every existing room). Delete the rooms first to change it.
        m = frappe.generate_hash(length=6)
        b = frappe.get_doc({
            "doctype": "Accommodation Building", "building_name": "QA Lock " + m,
            "abbreviation": "QA" + m[:2].upper(), "total_capacity": 10,
        })
        b.insert(ignore_permissions=True, ignore_links=True)
        room = frappe.get_doc({
            "doctype": "Accommodation Room", "naming_series": "ROOM-.####",
            "building": b.name, "room_number": b.abbreviation + "-G01",
        })
        room.insert(ignore_permissions=True, ignore_links=True)
        b.reload()
        b.abbreviation = "QANEW"
        with self.assertRaises(frappe.ValidationError):
            b.save(ignore_permissions=True)
        frappe.delete_doc("Accommodation Room", room.name, force=True, ignore_permissions=True)
        frappe.delete_doc("Accommodation Building", b.name, force=True, ignore_permissions=True)

    # --- P16 security / idempotency tests ------------------------------------

    def test_total_capacity_derives_from_beds(self):
        """total_capacity is the TRUE physical capacity: once rooms exist it must equal
        the sum of room bed_capacity (== physical bed count), overriding any manual
        figure, so the occupancy / cost / over-capacity denominators cannot drift."""
        from apex_habitat.habitat.doctype.accommodation_building.accommodation_building import (
            generate_rooms_and_beds,
        )
        m = frappe.generate_hash(length=6)
        b = frappe.get_doc({
            "doctype": "Accommodation Building",
            "building_name": "QA Capacity " + m,
            "abbreviation": "QC" + m[:2].upper(),
            "total_capacity": 999,  # deliberately wrong; must be overridden by derivation
            "floor_plan": [
                {"doctype": "Accommodation Floor Plan", "floor_number": 0, "room_count": 3,
                 "bed_capacity_per_room": 4, "room_type": "Standard", "generate_beds": 1,
                 "starting_room_number": 1},
                {"doctype": "Accommodation Floor Plan", "floor_number": 1, "room_count": 2,
                 "bed_capacity_per_room": 2, "room_type": "Standard", "generate_beds": 1,
                 "starting_room_number": 1},
            ],
        })
        b.insert(ignore_permissions=True, ignore_links=True)
        try:
            generate_rooms_and_beds(b.name)  # 3*4 + 2*2 = 16
            b.reload()
            bed_count = frappe.db.count("Accommodation Bed", {"building": b.name})
            self.assertEqual(b.total_capacity, 16, "total_capacity must derive to the bed-capacity sum")
            self.assertEqual(b.total_capacity, bed_count, "total_capacity must equal the physical bed count")
            # A subsequent save keeps it derived (before_save path), not the manual value.
            b.total_capacity = 5
            b.save(ignore_permissions=True)
            b.reload()
            self.assertEqual(b.total_capacity, 16, "before_save must re-derive total_capacity once rooms exist")
        finally:
            for room in frappe.db.get_all("Accommodation Room", {"building": b.name}, pluck="name"):
                for bed in frappe.db.get_all("Accommodation Bed", {"room": room}, pluck="name"):
                    frappe.delete_doc("Accommodation Bed", bed, force=True, ignore_permissions=True)
                frappe.delete_doc("Accommodation Room", room, force=True, ignore_permissions=True)
            frappe.delete_doc("Accommodation Building", b.name, force=True, ignore_permissions=True)

    def test_generate_rooms_and_beds_rejects_unauthorized_user(self):
        """Unauthorized user (Guest) must receive PermissionError from
        generate_rooms_and_beds, which guards with a doc-level write check."""
        from apex_habitat.habitat.doctype.accommodation_building.accommodation_building import (
            generate_rooms_and_beds,
        )
        m = frappe.generate_hash(length=6)
        b = frappe.get_doc({
            "doctype": "Accommodation Building",
            "building_name": "QA Perm Test " + m,
            "abbreviation": "QP" + m[:2].upper(),
            "total_capacity": 4,
        })
        b.insert(ignore_permissions=True, ignore_links=True)
        try:
            frappe.set_user("Guest")
            with self.assertRaises((frappe.PermissionError, frappe.exceptions.PermissionError)):
                generate_rooms_and_beds(b.name)
        finally:
            frappe.set_user("Administrator")
            frappe.delete_doc("Accommodation Building", b.name, force=True, ignore_permissions=True)

    def test_generate_rooms_and_beds_idempotent_no_duplicate_beds(self):
        """Re-running generate_rooms_and_beds must NOT create duplicate beds for
        existing rooms. The idempotency guard uses existing_bed_codes to skip any
        bed whose code is already present."""
        from apex_habitat.habitat.doctype.accommodation_building.accommodation_building import (
            generate_rooms_and_beds,
        )
        m = frappe.generate_hash(length=6)
        b = frappe.get_doc({
            "doctype": "Accommodation Building",
            "building_name": "QA Idempotent " + m,
            "abbreviation": "QI" + m[:2].upper(),
            "total_capacity": 2,
            "floor_plan": [
                {
                    "doctype": "Accommodation Floor Plan",
                    "floor_number": 0,
                    "room_count": 1,
                    "bed_capacity_per_room": 2,
                    "room_type": "Standard",
                    "generate_beds": 1,
                    "starting_room_number": 1,
                }
            ],
        })
        b.insert(ignore_permissions=True, ignore_links=True)
        try:
            # First run — creates rooms and beds
            generate_rooms_and_beds(b.name)
            beds_after_first = frappe.db.count(
                "Accommodation Bed",
                {"room": ["in", frappe.db.get_all(
                    "Accommodation Room", {"building": b.name}, pluck="name"
                )]},
            )
            # Second run with confirm — must NOT create duplicates
            r2 = generate_rooms_and_beds(b.name, confirm_new_rooms=1)
            beds_after_second = frappe.db.count(
                "Accommodation Bed",
                {"room": ["in", frappe.db.get_all(
                    "Accommodation Room", {"building": b.name}, pluck="name"
                )]},
            )
            self.assertEqual(
                beds_after_first, beds_after_second,
                "Re-running should not create duplicate beds"
            )
            self.assertEqual(r2.get("created_beds", 0), 0, "No new beds should be created on re-run")
            self.assertGreater(r2.get("skipped_beds", 0), 0, "Existing beds must be counted as skipped")
        finally:
            frappe.set_user("Administrator")
            rooms = frappe.db.get_all("Accommodation Room", {"building": b.name}, pluck="name")
            for room in rooms:
                beds = frappe.db.get_all("Accommodation Bed", {"room": room}, pluck="name")
                for bed in beds:
                    frappe.delete_doc("Accommodation Bed", bed, force=True, ignore_permissions=True)
                frappe.delete_doc("Accommodation Room", room, force=True, ignore_permissions=True)
            frappe.delete_doc("Accommodation Building", b.name, force=True, ignore_permissions=True)
