# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.tests.factories import make_building, make_room


class TestBuildingAbbreviationLock(FrappeTestCase):
    def test_changing_the_abbreviation_after_a_room_exists_is_refused(self):
        building = make_building("Test Building Abbrev Lock")
        building.abbreviation = "LOCK1"
        building.save(ignore_permissions=True)
        make_room(building.name, room_number=f"{building.name}-R99")

        building.reload()
        building.abbreviation = "LOCK2"
        with self.assertRaises(frappe.ValidationError):
            building.save(ignore_permissions=True)
