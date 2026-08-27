# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.habitat.doctype.bed.bed import toggle_service
from apex.tests.factories import make_building, make_room


def _room():
    building = make_building("Bed Contract Test Building", company="_Test Company")
    return make_room(building.name, room_number=f"{building.name}-BEDTEST")


def _bed(**overrides):
    fields = {
        "doctype": "Bed",
        "bed_code": "_T-Bed " + frappe.generate_hash(length=6),
        "room": None,
        "status": "Available",
    }
    fields.update(overrides)
    if "room" in fields and fields["room"] is None and "room" not in overrides:
        fields["room"] = _room().name
    return frappe.get_doc(fields)


class TestBedCodeIsTheRecordName(FrappeTestCase):
    def test_the_bed_code_becomes_the_record_name(self):
        doc = _bed().insert(ignore_permissions=True)
        self.assertEqual(doc.name, doc.bed_code)

    def test_framework_refuses_a_second_bed_carrying_the_same_code(self):
        first = _bed().insert(ignore_permissions=True)
        with self.assertRaises((frappe.DuplicateEntryError, frappe.UniqueValidationError)):
            _bed(bed_code=first.bed_code).insert(ignore_permissions=True)

    def test_the_naming_field_refuses_to_be_empty(self):
        with self.assertRaisesRegex(frappe.ValidationError, "Bed Code is required"):
            _bed(bed_code=None).insert(ignore_permissions=True)


class TestBedRoom(FrappeTestCase):
    def test_framework_refuses_a_bed_that_names_no_room(self):
        with self.assertRaises(frappe.MandatoryError):
            _bed(room="").insert(ignore_permissions=True)

    def test_the_building_is_fetched_from_the_room_without_the_operator_naming_it(self):
        room = _room()
        doc = _bed(room=room.name).insert(ignore_permissions=True)
        self.assertEqual(doc.building, frappe.db.get_value("Room", room.name, "building"))


class TestBedStatusVocabulary(FrappeTestCase):
    def test_framework_refuses_a_status_outside_the_select_options(self):
        with self.assertRaisesRegex(frappe.ValidationError, 'cannot be "Reserved"'):
            _bed(status="Reserved").insert(ignore_permissions=True)

    def test_the_declared_status_default_is_applied_server_side(self):
        doc = _bed(status=None).insert(ignore_permissions=True)
        self.assertEqual(doc.status, "Available")


class TestBedToggleService(FrappeTestCase):
    def test_an_occupied_bed_refuses_deactivation(self):
        doc = _bed().insert(ignore_permissions=True)
        doc.db_set("status", "Occupied")
        with self.assertRaisesRegex(
            frappe.ValidationError, "occupied. Check the resident out before deactivating it"
        ):
            toggle_service(doc.name)

    def test_an_occupied_bed_keeps_its_status_after_the_refusal(self):
        doc = _bed().insert(ignore_permissions=True)
        doc.db_set("status", "Occupied")
        with self.assertRaises(frappe.ValidationError):
            toggle_service(doc.name)
        self.assertEqual(frappe.db.get_value("Bed", doc.name, "status"), "Occupied")

    def test_an_available_bed_is_taken_out_of_service_in_the_database(self):
        doc = _bed().insert(ignore_permissions=True)
        self.assertEqual(toggle_service(doc.name), "Out of Service")
        self.assertEqual(frappe.db.get_value("Bed", doc.name, "status"), "Out of Service")

    def test_a_bed_out_of_service_is_returned_to_available(self):
        doc = _bed().insert(ignore_permissions=True)
        doc.db_set("status", "Out of Service")
        self.assertEqual(toggle_service(doc.name), "Available")
        self.assertEqual(frappe.db.get_value("Bed", doc.name, "status"), "Available")
