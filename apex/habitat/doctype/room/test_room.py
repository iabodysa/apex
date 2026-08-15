# Copyright (c) 2026, afmcoltd
"""Room's own contract: it needs a building, and it takes the room number it is given.

Frappe stands the Building up from its ``test_records.json`` before this module runs, so nothing
here builds one. That is the whole point of ``test_dependencies``: the record exists once per suite
run rather than once per test.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

test_dependencies = ["Building"]


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
