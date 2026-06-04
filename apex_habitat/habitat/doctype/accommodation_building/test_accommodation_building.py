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
