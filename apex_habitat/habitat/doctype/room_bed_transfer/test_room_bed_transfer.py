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


class TestRoomBedTransfer(FrappeTestCase):

    def _h(self):
        return frappe.generate_hash(length=4).upper()

    def _fixtures(self):
        """Real building/room/bed/assignment so validate() runs in full: the target
        room MUST carry a building, otherwise the integrity guard rightly rejects it."""
        company = frappe.db.get_value("Company", {}) or frappe.get_doc({
            "doctype": "Company", "company_name": "Test Co", "default_currency": "SAR",
            "country": "Saudi Arabia"}).insert(ignore_permissions=True).name
        cc = frappe.db.get_value("Cost Center", {"is_group": 0, "company": company}) or frappe.db.get_value("Cost Center", {"is_group": 0})
        site = frappe.get_doc({"doctype": "Accommodation Site", "site_name": self._h() + self._h()}).insert(ignore_permissions=True).name
        building = frappe.get_doc({"doctype": "Accommodation Building", "building_name": "B " + self._h(),
                                   "site": site, "total_capacity": 4, "company": company,
                                   "default_cost_center": cc}).insert(ignore_permissions=True).name
        room = frappe.get_doc({"doctype": "Accommodation Room", "naming_series": "ROOM-.####", "building": building,
                               "room_number": "R" + self._h(), "bed_capacity": 4,
                               "readiness_status": "Ready"}).insert(ignore_permissions=True).name
        bed = frappe.get_doc({"doctype": "Accommodation Bed", "naming_series": "BED-.####", "room": room,
                              "building": building, "bed_code": "B" + self._h(),
                              "status": "Available"}).insert(ignore_permissions=True).name
        emp = frappe.get_doc({"doctype": "Employee", "first_name": "E " + self._h(), "company": company,
                              "gender": "Male", "date_of_birth": "1990-01-01",
                              "date_of_joining": "2020-01-01"}).insert(ignore_permissions=True).name
        project = frappe.get_doc({"doctype": "Project", "project_name": "P " + self._h()}).insert(ignore_permissions=True).name
        assignment = frappe.get_doc({"doctype": "Accommodation Assignment", "naming_series": "ACC-ASGN-.YYYY.-.####",
                                     "employee": emp, "project": project, "building": building, "room": room,
                                     "bed": bed, "cost_center": cc, "check_in_date": "2026-06-01",
                                     "assignment_type": "New Assignment"}).insert(ignore_permissions=True).name
        return frappe._dict(building=building, room=room, bed=bed, assignment=assignment)

    def test_create_valid_transfer(self):
        fx = self._fixtures()
        doc = frappe.get_doc({
            "doctype": "Room Bed Transfer",
            "naming_series": "RBT-.YYYY.-.####",
            "assignment": fx.assignment,
            "to_room": fx.room,
            "to_bed": fx.bed,
            "transfer_date": "2026-06-01",
        })
        doc.insert(ignore_permissions=True)
        self.assertIsNotNone(doc.name)
        frappe.delete_doc("Room Bed Transfer", doc.name, force=True, ignore_permissions=True)

    def test_missing_assignment_raises(self):
        fx = self._fixtures()
        doc = frappe.get_doc({
            "doctype": "Room Bed Transfer",
            "naming_series": "RBT-.YYYY.-.####",
            "to_room": fx.room,
            "to_bed": fx.bed,
            "transfer_date": "2026-06-01",
        })
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert(ignore_permissions=True)

    def test_missing_transfer_date_raises(self):
        fx = self._fixtures()
        doc = frappe.get_doc({
            "doctype": "Room Bed Transfer",
            "naming_series": "RBT-.YYYY.-.####",
            "assignment": fx.assignment,
            "to_room": fx.room,
            "to_bed": fx.bed,
        })
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert(ignore_permissions=True)

    def test_transfer_to_room_without_building_is_rejected(self):
        """RED->GREEN for the building-integrity guard: a transfer whose target room
        carries no building must be rejected in validate(). The room is minted with
        ignore_mandatory (building is reqd in the UI) + the field is cleared to be
        certain, and its bed is Available and belongs to the room, so every earlier
        validate gate passes and execution reaches the building guard."""
        fx = self._fixtures()
        no_bldg_room = frappe.get_doc({
            "doctype": "Accommodation Room", "naming_series": "ROOM-.####",
            "room_number": "NB" + self._h(), "bed_capacity": 1,
            "readiness_status": "Ready"}).insert(ignore_permissions=True, ignore_mandatory=True).name
        # Be certain the guard sees an unset building even if a default crept in.
        frappe.db.set_value("Accommodation Room", no_bldg_room, "building", None, update_modified=False)
        no_bldg_bed = frappe.get_doc({
            "doctype": "Accommodation Bed", "naming_series": "BED-.####", "room": no_bldg_room,
            "bed_code": "NB" + self._h(),
            "status": "Available"}).insert(ignore_permissions=True, ignore_mandatory=True).name

        doc = frappe.get_doc({
            "doctype": "Room Bed Transfer",
            "naming_series": "RBT-.YYYY.-.####",
            "assignment": fx.assignment,
            "to_room": no_bldg_room,
            "to_bed": no_bldg_bed,
            "transfer_date": "2026-06-03",
        })
        with self.assertRaises(frappe.ValidationError):
            doc.insert(ignore_permissions=True)

        frappe.delete_doc("Accommodation Bed", no_bldg_bed, force=True, ignore_permissions=True)
        frappe.delete_doc("Accommodation Room", no_bldg_room, force=True, ignore_permissions=True)

    def test_cancel_restores_assignment_to_origin(self):
        """RED->GREEN: submitting a transfer moves the assignment onto the target
        bed/room/building; cancelling must reverse the move and restore the origin
        bed/room/building (re-occupy origin bed, free target). origin == fx.bed/
        room/building; target == a second Available bed in the same room."""
        fx = self._fixtures()
        target_bed = frappe.get_doc({
            "doctype": "Accommodation Bed", "naming_series": "BED-.####", "room": fx.room,
            "building": fx.building, "bed_code": "T" + self._h(),
            "status": "Available"}).insert(ignore_permissions=True).name

        asg = frappe.get_doc("Accommodation Assignment", fx.assignment)
        asg.submit()  # origin bed -> Occupied, assignment active (checked-in)

        transfer = frappe.get_doc({
            "doctype": "Room Bed Transfer",
            "naming_series": "RBT-.YYYY.-.####",
            "assignment": fx.assignment,
            "to_room": fx.room,
            "to_bed": target_bed,
            "transfer_date": "2026-06-02",
        })
        transfer.insert(ignore_permissions=True)
        transfer.submit()

        asg.reload()
        self.assertEqual(asg.bed, target_bed, "submit moves the assignment onto the target bed")
        self.assertEqual(frappe.db.get_value("Accommodation Bed", target_bed, "status"), "Occupied")
        self.assertEqual(frappe.db.get_value("Accommodation Bed", fx.bed, "status"), "Available")

        transfer.cancel()

        asg.reload()
        self.assertEqual(asg.bed, fx.bed, "cancel restores the origin bed onto the assignment")
        self.assertEqual(asg.room, fx.room, "cancel restores the origin room")
        self.assertEqual(asg.building, fx.building, "cancel restores the origin building")
        self.assertEqual(frappe.db.get_value("Accommodation Bed", fx.bed, "status"), "Occupied",
                         "origin bed is re-occupied on cancel")
        self.assertEqual(frappe.db.get_value("Accommodation Bed", target_bed, "status"), "Available",
                         "target bed is freed on cancel")
