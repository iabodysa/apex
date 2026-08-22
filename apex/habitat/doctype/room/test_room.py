# Copyright (c) 2026, afmcoltd
"""Room's own contract: it needs a building, and it takes the room number it is given.

Frappe stands the Building up from its ``test_records.json`` before this module runs, so nothing
here builds one. That is the whole point of ``test_dependencies``: the record exists once per suite
run rather than once per test.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
import json
from pathlib import Path
from unittest import TestCase
from apex.habitat.doctype.building import building

class TestRoom(FrappeTestCase):
    def test_a_room_takes_the_number_it_is_given(self):
        room = frappe.get_doc({
            "doctype": "Room",
            "naming_series": "ROOM-.####",
            "building": "_Test Building",
            "room_number": "_T-R101",
            "bed_capacity": 4,
        })
        room.insert(ignore_permissions=True)
        self.addCleanup(frappe.delete_doc, "Room", room.name, force=True, ignore_permissions=True)

        self.assertEqual(room.room_number, "_T-R101")
        self.assertEqual(room.building, "_Test Building")

    def test_a_room_without_a_building_is_refused(self):
        room = frappe.get_doc({
            "doctype": "Room",
            "naming_series": "ROOM-.####",
            "room_number": "_T-R999",
            "bed_capacity": 2,
        })

        with self.assertRaises(frappe.exceptions.MandatoryError):
            room.insert(ignore_permissions=True)

test_dependencies = ['Building']

class TestRoomSearchFieldsResolve(TestCase):
    def _meta(self):
        return json.loads(
            (Path(__file__).with_name("room.json")).read_text(encoding="utf-8")
        )

    def test_every_search_field_is_a_field_of_room(self):
        meta = self._meta()
        fieldnames = {field["fieldname"] for field in meta["fields"]} | {"name"}
        searched = [part.strip() for part in meta["search_fields"].split(",")]

        self.assertTrue(searched, "the list view still searches on something")
        self.assertEqual(
            [name for name in searched if name not in fieldnames],
            [],
            "search_fields names a column the DocType does not have",
        )

    def test_no_write_only_inventory_stamp_survives(self):
        self.assertNotIn(
            "last_inventory_date",
            {field["fieldname"] for field in self._meta()["fields"]},
            "the field's only writer was deleted; a field nothing can write is not a record",
        )

    def test_building_publishes_no_second_room_readiness_writer(self):
        self.assertFalse(
            hasattr(building, "update_room_inventory"),
            "readiness is set through front_desk.set_room_readiness, which has callers",
        )
