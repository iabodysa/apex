# Copyright (c) 2026, AFMCO and contributors
import frappe
from frappe.tests.utils import FrappeTestCase

# [#8evoal]
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
            "doctype": "Building",
            "building_name": "QA Test Building",
            "total_capacity": 20,
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.assertEqual(doc.building_name, "QA Test Building")
        frappe.delete_doc("Building", doc.name, force=True, ignore_permissions=True)

    def test_missing_building_name_raises(self):
        doc = frappe.get_doc({
            "doctype": "Building",
            "total_capacity": 10,
        })
        with self.assertRaises(frappe.exceptions.ValidationError):
            doc.insert(ignore_permissions=True, ignore_links=True)

    def test_new_building_saves_without_manual_capacity(self):
        """total_capacity is system-derived (read-only, not reqd): a brand-new building
        with NO rooms/beds yet must still save, defaulting the capacity to 0 rather than
        raising MandatoryError (a read-only reqd Int could never be filled on a new doc)."""
        doc = frappe.get_doc({
            "doctype": "Building",
            "building_name": "QA No Manual Capacity",
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        try:
            self.assertEqual(doc.total_capacity, 0, "no beds yet -> capacity defaults to 0")
            self.assertEqual(
                frappe.get_meta("Building").get_field("total_capacity").reqd, 0,
                "total_capacity must no longer be reqd (it is system-derived)",
            )
        finally:
            frappe.delete_doc("Building", doc.name, force=True, ignore_permissions=True)

    # [#gbkzzh]
    def test_room_number_blank_prefix_is_byte_identical(self):
        from apex.habitat.doctype.building.building import _room_number
        # [#t4isrx]
        self.assertEqual(_room_number("JED1", "G", "", 1), "JED1-G01")
        self.assertEqual(_room_number("JED1", "1", "", 5), "JED1-105")

    def test_room_number_with_prefix(self):
        from apex.habitat.doctype.building.building import _room_number
        self.assertEqual(_room_number("JED1", "G", "A", 1), "JED1-GA01")
        self.assertEqual(_room_number("JED1", "1", "B", 5), "JED1-1B05")
        self.assertEqual(_room_number("JED1", "G", " A ", 1), "JED1-GA01")  # [#h85o05]

    def test_abbreviation_locked_after_rooms_exist(self):
        # [#r0twhb]
        m = frappe.generate_hash(length=12)
        b = frappe.get_doc({
            "doctype": "Building", "building_name": "QA Lock " + m,
            "abbreviation": "QA" + m[:2].upper(), "total_capacity": 10,
        })
        b.insert(ignore_permissions=True, ignore_links=True)
        room = frappe.get_doc({
            "doctype": "Room", "naming_series": "ROOM-.####",
            "building": b.name, "room_number": b.abbreviation + "-G01",
        })
        room.insert(ignore_permissions=True, ignore_links=True)
        b.reload()
        b.abbreviation = "QANEW"
        with self.assertRaises(frappe.ValidationError):
            b.save(ignore_permissions=True)
        frappe.delete_doc("Room", room.name, force=True, ignore_permissions=True)
        frappe.delete_doc("Building", b.name, force=True, ignore_permissions=True)

    # [#1nwoc6]

    def test_total_capacity_derives_from_beds(self):
        """total_capacity is the TRUE physical capacity: it must equal the count of the
        building's ACTUAL beds that are not Out of Service (and not virtual over-capacity
        beds), overriding any manual figure, so the occupancy / cost / over-capacity
        denominators cannot drift. Setting one bed Out of Service drops capacity by 1.
        The field is also read-only (system-derived)."""
        from apex.habitat.doctype.building.building import (
            generate_rooms_and_beds,
        )
        # [#gckv3l]
        self.assertEqual(
            frappe.get_meta("Building").get_field("total_capacity").read_only, 1,
            "total_capacity must be read_only (auto-derived)",
        )
        m = frappe.generate_hash(length=12)
        b = frappe.get_doc({
            "doctype": "Building",
            "building_name": "QA Capacity " + m,
            "abbreviation": "QC" + m[:2].upper(),
            "total_capacity": 999,  # [#8yikf3]
            "floor_plan": [
                {"doctype": "Floor Plan", "floor_number": 0, "room_count": 3,
                 "bed_capacity_per_room": 4, "room_type": "Standard", "generate_beds": 1,
                 "starting_room_number": 1},
                {"doctype": "Floor Plan", "floor_number": 1, "room_count": 2,
                 "bed_capacity_per_room": 2, "room_type": "Standard", "generate_beds": 1,
                 "starting_room_number": 1},
            ],
        })
        b.insert(ignore_permissions=True, ignore_links=True)
        try:
            generate_rooms_and_beds(b.name)  # [#y61kin]
            b.reload()
            available_beds = frappe.db.count(
                "Bed",
                {"building": b.name, "status": ["!=", "Out of Service"], "is_temporary": 0},
            )
            self.assertEqual(b.total_capacity, 16, "total_capacity must derive to the physical bed count")
            self.assertEqual(available_beds, 16, "fixture sanity: 16 available physical beds")
            self.assertEqual(b.total_capacity, available_beds,
                             "total_capacity must equal the non-Out-of-Service physical bed count")
            # [#31yd6i]
            one_bed = frappe.db.get_value("Bed", {"building": b.name}, "name")
            frappe.db.set_value("Bed", one_bed, "status", "Out of Service")
            b.save(ignore_permissions=True)
            b.reload()
            self.assertEqual(b.total_capacity, 15,
                             "an Out-of-Service bed must be excluded -> capacity drops by 1")
            # [#lnc287]
            b.total_capacity = 5
            b.save(ignore_permissions=True)
            b.reload()
            self.assertEqual(b.total_capacity, 15, "before_save must re-derive, ignoring the manual value")
        finally:
            for room in frappe.db.get_all("Room", {"building": b.name}, pluck="name"):
                for bed in frappe.db.get_all("Bed", {"room": room}, pluck="name"):
                    frappe.delete_doc("Bed", bed, force=True, ignore_permissions=True)
                frappe.delete_doc("Room", room, force=True, ignore_permissions=True)
            frappe.delete_doc("Building", b.name, force=True, ignore_permissions=True)

    def test_no_bed_room_does_not_inflate_capacity(self):
        """The core T-136 fix: a room with generate_beds=0 has a planned bed_capacity but
        NO physical beds. Deriving from sum(bed_capacity) over-counted it; deriving from
        the actual beds must NOT — total_capacity counts only the beds that truly exist."""
        from apex.habitat.doctype.building.building import (
            generate_rooms_and_beds,
        )
        m = frappe.generate_hash(length=12)
        b = frappe.get_doc({
            "doctype": "Building",
            "building_name": "QA NoBed " + m,
            "abbreviation": "QN" + m[:2].upper(),
            "total_capacity": 999,
            "floor_plan": [
                # [#jm2kdt]
                {"doctype": "Floor Plan", "floor_number": 0, "room_count": 2,
                 "bed_capacity_per_room": 3, "room_type": "Standard", "generate_beds": 1,
                 "starting_room_number": 1},
                # [#51d1s7]
                {"doctype": "Floor Plan", "floor_number": 1, "room_count": 2,
                 "bed_capacity_per_room": 5, "room_type": "Office", "generate_beds": 0,
                 "starting_room_number": 1},
            ],
        })
        b.insert(ignore_permissions=True, ignore_links=True)
        try:
            generate_rooms_and_beds(b.name)
            b.reload()
            bed_count = frappe.db.count("Bed", {"building": b.name})
            self.assertEqual(bed_count, 6, "only the generate_beds=1 rooms mint physical beds")
            self.assertEqual(b.total_capacity, 6,
                             "no-bed rooms must NOT inflate capacity (old sum() would give 16)")
        finally:
            for room in frappe.db.get_all("Room", {"building": b.name}, pluck="name"):
                for bed in frappe.db.get_all("Bed", {"room": room}, pluck="name"):
                    frappe.delete_doc("Bed", bed, force=True, ignore_permissions=True)
                frappe.delete_doc("Room", room, force=True, ignore_permissions=True)
            frappe.delete_doc("Building", b.name, force=True, ignore_permissions=True)

    def test_cctv_camera_count_derives_from_facility_assets(self):
        """cctv_camera_count auto-counts the building's CCTV Camera Facility Assets,
        excluding retired ones (Replaced/Scrapped), and is read-only — so a manual
        value is overridden on save."""
        self.assertEqual(
            frappe.get_meta("Building").get_field("cctv_camera_count").read_only, 1,
            "cctv_camera_count must be read_only (auto-derived)",
        )
        m = frappe.generate_hash(length=12)
        b = frappe.get_doc({
            "doctype": "Building",
            "building_name": "QA CCTV " + m,
            "cctv_camera_count": 99,  # manual value must be overridden
        })
        b.insert(ignore_permissions=True, ignore_links=True)
        cams = []
        try:
            for i, status in enumerate(("Operational", "Faulty", "Scrapped")):
                cam = frappe.get_doc({
                    "doctype": "Facility Asset",
                    "naming_series": "FAC-AST-.YYYY.-.####",
                    "asset_name": f"QA Cam {m} {i}",
                    "asset_category": "CCTV Camera",
                    "building": b.name,
                    "status": status,
                    "responsible_supervisor": "Administrator",
                })
                cam.insert(ignore_permissions=True, ignore_links=True)
                cams.append(cam.name)
            # a non-CCTV asset must not be counted
            other = frappe.get_doc({
                "doctype": "Facility Asset",
                "naming_series": "FAC-AST-.YYYY.-.####",
                "asset_name": f"QA Gen {m}",
                "asset_category": "Generator",
                "building": b.name,
                "responsible_supervisor": "Administrator",
            })
            other.insert(ignore_permissions=True, ignore_links=True)
            cams.append(other.name)

            b.save(ignore_permissions=True)
            b.reload()
            self.assertEqual(
                b.cctv_camera_count, 2,
                "counts Operational + Faulty CCTV cameras; excludes Scrapped and the Generator",
            )
        finally:
            for name in cams:
                frappe.delete_doc("Facility Asset", name, force=True, ignore_permissions=True)
            frappe.delete_doc("Building", b.name, force=True, ignore_permissions=True)

    def test_generate_rooms_and_beds_rejects_unauthorized_user(self):
        """Unauthorized user (Guest) must receive PermissionError from
        generate_rooms_and_beds, which guards with a doc-level write check."""
        from apex.habitat.doctype.building.building import (
            generate_rooms_and_beds,
        )
        m = frappe.generate_hash(length=12)
        b = frappe.get_doc({
            "doctype": "Building",
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
            frappe.delete_doc("Building", b.name, force=True, ignore_permissions=True)

    def test_generate_rooms_and_beds_idempotent_no_duplicate_beds(self):
        """Re-running generate_rooms_and_beds must NOT create duplicate beds for
        existing rooms. The idempotency guard uses existing_bed_codes to skip any
        bed whose code is already present."""
        from apex.habitat.doctype.building.building import (
            generate_rooms_and_beds,
        )
        m = frappe.generate_hash(length=12)
        b = frappe.get_doc({
            "doctype": "Building",
            "building_name": "QA Idempotent " + m,
            "abbreviation": "QI" + m[:2].upper(),
            "total_capacity": 2,
            "floor_plan": [
                {
                    "doctype": "Floor Plan",
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
            # [#klflrr]
            generate_rooms_and_beds(b.name)
            beds_after_first = frappe.db.count(
                "Bed",
                {"room": ["in", frappe.db.get_all(
                    "Room", {"building": b.name}, pluck="name"
                )]},
            )
            # [#2f8hc7]
            r2 = generate_rooms_and_beds(b.name, confirm_new_rooms=1)
            beds_after_second = frappe.db.count(
                "Bed",
                {"room": ["in", frappe.db.get_all(
                    "Room", {"building": b.name}, pluck="name"
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
            rooms = frappe.db.get_all("Room", {"building": b.name}, pluck="name")
            for room in rooms:
                beds = frappe.db.get_all("Bed", {"room": room}, pluck="name")
                for bed in beds:
                    frappe.delete_doc("Bed", bed, force=True, ignore_permissions=True)
                frappe.delete_doc("Room", room, force=True, ignore_permissions=True)
            frappe.delete_doc("Building", b.name, force=True, ignore_permissions=True)
