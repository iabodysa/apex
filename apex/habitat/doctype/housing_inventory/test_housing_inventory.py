# Copyright (c) 2026, afmcoltd
"""``building`` is ``fetch_from: room.building`` and carries no ``fetch_if_empty``,
so the room OWNS it: every save overwrites a declared building with the room's own
(frappe/model/base_document.py:820-826, inside ``_validate_links``, which runs on
every write path — desk, Data Import, API). A row whose room and building disagree
is therefore not refused, it is impossible. Building-level stock keeps a hand-set
building because the fetch only fires when ``room`` holds a value.

``test_ignore`` names ``Facility Asset`` and ``Maintenance Work Order``:
``get_dependencies`` (frappe/test_runner.py:359-381) builds a test record for every
Link on the DocType under test whether or not a case touches it, and both of those
Link chains reach ERPNext's ``Payment Gateway Account`` and through it ``Payment
Gateway``, which the ``payments`` app owns and a site need not install — so the walk
aborts the WHOLE suite before one case runs. ``test_ignore``
(test_runner.py:374-377) is the framework's own hatch, scoped to this module.
Nothing below reads either field.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

test_ignore = ["Facility Asset", "Maintenance Work Order"]


class TestTheRoomOwnsTheBuilding(FrappeTestCase):
    def _row(self, **fields):
        doc = frappe.get_doc(
            {
                "doctype": "Housing Inventory",
                "item_name": "_T-Inventory-Item",
                "item_category": "Furniture",
            }
        )
        doc.update(fields)
        return doc

    def test_a_building_that_disagrees_with_the_room_is_overwritten(self):
        room_building = frappe.db.get_value("Room", "_T-101", "building")
        self.assertEqual(room_building, "_Test Building")

        doc = self._row(room="_T-101", building="_Test Building 2")
        doc.insert()
        self.addCleanup(frappe.delete_doc, "Housing Inventory", doc.name, force=True)
        self.assertEqual(doc.building, room_building)

    def test_a_blank_building_is_filled_from_the_room(self):
        doc = self._row(room="_T-101")
        doc.insert()
        self.addCleanup(frappe.delete_doc, "Housing Inventory", doc.name, force=True)
        self.assertEqual(doc.building, "_Test Building")

    def test_building_level_stock_keeps_its_own_building(self):
        """No room, so the fetch never fires and the hand-set building stands."""
        doc = self._row(building="_Test Building 2")
        doc.insert()
        self.addCleanup(frappe.delete_doc, "Housing Inventory", doc.name, force=True)
        self.assertEqual(doc.building, "_Test Building 2")
