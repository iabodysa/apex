# Copyright (c) 2026, afmcoltd


import frappe
from frappe.tests.utils import FrappeTestCase

from apex.habitat.doctype.housing_assignment.housing_assignment import (
    _derive_place_from_bed,
)


def _bed_with_a_building():
    for bed in frappe.get_all("Bed", pluck="name"):
        room = frappe.db.get_value("Bed", bed, "room")
        if room and frappe.db.get_value("Room", room, "building"):
            return bed, room, frappe.db.get_value("Room", room, "building")
    return None, None, None


class TestPlaceIsDerivedFromTheBed(FrappeTestCase):
    def test_both_hops_fill_from_the_bed_alone(self):
        bed, room, building = _bed_with_a_building()
        self.assertIsNotNone(bed, "no bed on this site names a room that names a building")

        doc = frappe._dict(bed=bed, room=None, building=None)
        _derive_place_from_bed(doc)
        self.assertEqual(doc.room, room)
        self.assertEqual(doc.building, building)

    def test_a_caller_supplied_value_is_never_overwritten(self):
        bed, room, _building = _bed_with_a_building()
        self.assertIsNotNone(bed)

        doc = frappe._dict(bed=bed, room=room, building="Chosen By Caller")
        _derive_place_from_bed(doc)
        self.assertEqual(doc.building, "Chosen By Caller")

    def test_no_bed_derives_nothing_rather_than_guessing(self):
        doc = frappe._dict(bed=None, room=None, building=None)
        _derive_place_from_bed(doc)
        self.assertIsNone(doc.room)
        self.assertIsNone(doc.building)

    def test_the_chain_still_does_not_resolve_on_its_own(self):
        doc = frappe.get_doc({"doctype": "Housing Assignment"})
        bed, _room, _building = _bed_with_a_building()
        doc.bed = bed
        if hasattr(doc, "set_fetch_from_values"):
            doc.set_fetch_from_values()
        self.assertIsNone(
            doc.get("building"),
            "fetch_from now cascades server-side — _derive_place_from_bed is redundant",
        )
