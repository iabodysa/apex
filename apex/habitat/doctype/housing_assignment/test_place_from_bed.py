# Copyright (c) 2026, afmcoltd

"""An assignment created in code must know its building, exactly as one typed does.

``building`` fetches from ``room.building`` and ``room`` fetches from ``bed.room`` — a
two-hop ``fetch_from`` chain. A chain only resolves in the desk, where the browser
fetches one hop, writes the field, and the next hop fires off that write. On the server
each ``fetch_from`` resolves once against the values present when validation starts, so
the second hop reads a room that is still blank and building never fills.

Every desk save therefore worked while every programmatic one — an API call, an import, a
scheduled job, the demo builder — produced an assignment with no building. The controller
returns early on a blank building, so such a row skipped its cost centre, its capacity
check and its duplicate-occupancy check in silence; only ``reqd`` on the field turned that
into a refusal rather than a bad row.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.habitat.doctype.housing_assignment.housing_assignment import (
    _derive_place_from_bed,
)


def _bed_with_a_building():
    """Any bed whose room names a building, or None when the site has none."""
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
        """A transfer names the destination explicitly; deriving over it would send the
        worker back to the bed they came from."""
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
        """The positive control for the whole file: if Frappe ever starts cascading
        fetch_from server-side, this fails and the derivation can be deleted."""
        doc = frappe.get_doc({"doctype": "Housing Assignment"})
        bed, _room, _building = _bed_with_a_building()
        doc.bed = bed
        if hasattr(doc, "set_fetch_from_values"):
            doc.set_fetch_from_values()
        self.assertIsNone(
            doc.get("building"),
            "fetch_from now cascades server-side — _derive_place_from_bed is redundant",
        )
