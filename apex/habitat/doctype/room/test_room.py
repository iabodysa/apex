# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.habitat.doctype.room.room import toggle_service
from apex.tests.factories import make_assignment, make_building, make_employee, make_project


def _building():
    return make_building("Room Contract Test Building", company="_Test Company")


def _room(**overrides):
    fields = {
        "doctype": "Room",
        "room_number": "_T-Room " + frappe.generate_hash(length=6),
        "building": None,
        "bed_capacity": 2,
    }
    fields.update(overrides)
    if fields.get("building") is None:
        fields["building"] = _building().name
    return frappe.get_doc(fields)


class TestRoomNumberIsTheRecordName(FrappeTestCase):
    def test_the_room_number_becomes_the_record_name(self):
        doc = _room().insert(ignore_permissions=True)
        self.assertEqual(doc.name, doc.room_number)

    def test_framework_refuses_a_second_room_carrying_the_same_number(self):
        first = _room().insert(ignore_permissions=True)
        with self.assertRaises((frappe.DuplicateEntryError, frappe.UniqueValidationError)):
            _room(room_number=first.room_number).insert(ignore_permissions=True)

    def test_the_naming_field_refuses_to_be_empty(self):
        with self.assertRaisesRegex(frappe.ValidationError, "Room Number is required"):
            _room(room_number=None).insert(ignore_permissions=True)


class TestRoomBuilding(FrappeTestCase):
    def test_framework_refuses_a_room_that_names_no_building(self):
        with self.assertRaises(frappe.MandatoryError):
            _room(building="").insert(ignore_permissions=True)

    def test_framework_refuses_a_building_that_does_not_exist(self):
        with self.assertRaisesRegex(frappe.LinkValidationError, "Could not find"):
            _room(building="No Such Building " + frappe.generate_hash(length=6)).insert(
                ignore_permissions=True
            )


class TestRoomVocabularyAndDefaults(FrappeTestCase):
    def test_framework_refuses_a_room_type_outside_the_select_options(self):
        with self.assertRaisesRegex(frappe.ValidationError, 'cannot be "Penthouse"'):
            _room(room_type="Penthouse").insert(ignore_permissions=True)

    def test_a_new_room_starts_with_an_unknown_readiness_rather_than_ready(self):
        doc = _room().insert(ignore_permissions=True)
        self.assertEqual(doc.readiness_status, "Unknown")


class TestRoomToggleService(FrappeTestCase):
    def _occupied_room(self):
        building = _building()
        project = make_project("Room Contract Test Project")
        employee = make_employee(
            "Room Contract Test Resident " + frappe.generate_hash(length=6), company="_Test Company"
        )
        room_number = "_T-Room " + frappe.generate_hash(length=6)
        make_assignment(
            employee.name,
            building.name,
            project,
            room_number=room_number,
            bed_code="_T-Bed " + frappe.generate_hash(length=6),
        )
        return room_number

    def test_a_room_holding_a_current_occupant_refuses_deactivation(self):
        room = self._occupied_room()
        with self.assertRaisesRegex(
            frappe.ValidationError, "current occupant\\(s\\). Check them out before deactivating it"
        ):
            toggle_service(room)

    def test_a_room_holding_a_current_occupant_keeps_its_readiness_after_the_refusal(self):
        room = self._occupied_room()
        before = frappe.db.get_value("Room", room, "readiness_status")
        with self.assertRaises(frappe.ValidationError):
            toggle_service(room)
        self.assertEqual(frappe.db.get_value("Room", room, "readiness_status"), before)

    def test_an_empty_room_is_taken_out_of_service_in_the_database(self):
        doc = _room().insert(ignore_permissions=True)
        self.assertEqual(toggle_service(doc.name), "Out of Service")
        self.assertEqual(frappe.db.get_value("Room", doc.name, "readiness_status"), "Out of Service")

    def test_a_room_out_of_service_is_returned_to_ready_without_an_occupancy_check(self):
        doc = _room().insert(ignore_permissions=True)
        doc.db_set("readiness_status", "Out of Service")
        self.assertEqual(toggle_service(doc.name), "Ready")
        self.assertEqual(frappe.db.get_value("Room", doc.name, "readiness_status"), "Ready")
