# Copyright (c) 2026, afmcoltd
"""What Cleaning Log guarantees, asserted against the DocType itself.

Patterned on ``frappe/tests/test_document.py`` — the subject is ``before_submit``,
``on_submit`` and ``on_cancel``. Submitting is the audit-evidence commit: each of the
three required areas (Bathrooms, Kitchen, Corridors) must carry either a Cleaned photo
or a Not Cleaned/N/A note before submit is allowed, and any photo row missing its
server stamp gets ``captured_at`` set from the server rather than the client. On submit
the log posts one Cleaning Compliance Ledger row per room-detail child row; on cancel
it reverses every row it posted.

Each case builds on a throwaway Building: ``on_doctype_update`` enforces one
non-cancelled Cleaning Log per (building, cleaning_date), and this DocType's own test
class shares one transaction across its methods (`FrappeTestCase` rolls back once at
class teardown), so reusing a fixture building/date across cases would collide.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

test_dependencies = ["Building", "Room", "Employee"]


def _fresh_building_and_room():
    """A throwaway Building (with one Room) unique to the calling test."""
    building = frappe.copy_doc(frappe.get_test_records("Building")[0])
    building.building_name = f"_T-Cleaning Building {frappe.generate_hash(length=8)}"
    building.floor_plan = []
    building.insert()
    room = frappe.get_doc(
        {
            "doctype": "Room",
            "building": building.name,
            "room_number": f"_T-Cleaning-Room-{frappe.generate_hash(length=6)}",
        }
    ).insert()
    return building.name, room.name


def _new_log(building):
    record = frappe.copy_doc(frappe.get_test_records("Cleaning Log")[0])
    record.building = building
    record.cleaning_date = "2026-01-10"
    record.area_photos = []
    return record


def _full_area_evidence(record):
    """The minimum evidence that satisfies all three required areas."""
    record.append(
        "area_photos", {"area": "Bathrooms", "status": "Cleaned", "photo": "/files/bath.jpg"}
    )
    record.append(
        "area_photos", {"area": "Kitchen", "status": "Cleaned", "photo": "/files/kitchen.jpg"}
    )
    record.append(
        "area_photos",
        {"area": "Corridors", "status": "Not Cleaned", "note": "Corridor locked for repairs"},
    )


class TestCleaningLog(FrappeTestCase):
    def test_submit_is_refused_when_a_required_area_has_no_evidence_at_all(self):
        """An area with no row at all cannot have been checked."""
        building, _room = _fresh_building_and_room()
        record = _new_log(building)
        record.append(
            "area_photos", {"area": "Bathrooms", "status": "Cleaned", "photo": "/files/bath.jpg"}
        )
        record.append(
            "area_photos", {"area": "Kitchen", "status": "Cleaned", "photo": "/files/kitchen.jpg"}
        )
        record.insert()

        with self.assertRaisesRegex(frappe.ValidationError, "Corridors.*required before submit"):
            record.submit()

    def test_submit_is_refused_when_an_area_is_neither_photographed_nor_excused(self):
        """A status of Not Cleaned / N/A with no note excuses nothing."""
        building, _room = _fresh_building_and_room()
        record = _new_log(building)
        _full_area_evidence(record)
        record.area_photos[-1].note = ""
        record.insert()

        with self.assertRaisesRegex(frappe.ValidationError, "Corridors"):
            record.submit()

    def test_submit_is_accepted_with_full_evidence_and_stamps_the_photo_rows(self):
        """The acceptance case: full evidence submits, and an unstamped photo gets a server stamp."""
        building, room = _fresh_building_and_room()
        record = _new_log(building)
        _full_area_evidence(record)
        record.append("room_details", {"room": room, "room_status": "Cleaned", "cleaned": 1})
        record.insert()
        self.assertIsNone(record.area_photos[0].captured_at)

        record.submit()

        self.assertIsNotNone(
            record.area_photos[0].captured_at,
            "a photo row's capture time must be stamped by the server, not left blank",
        )

    def test_on_submit_posts_one_ledger_row_per_room_and_on_cancel_reverses_it(self):
        """The compliance ledger must gain exactly what submit posted, and lose none of it on cancel."""
        building, room = _fresh_building_and_room()
        record = _new_log(building)
        _full_area_evidence(record)
        record.append("room_details", {"room": room, "room_status": "Cleaned", "cleaned": 1})
        record.insert()

        record.submit()
        posted = frappe.get_all(
            "Cleaning Compliance Ledger",
            filters={"source_name": record.name, "is_cancelled": 0},
            fields=["name", "room", "cleaned", "building"],
        )
        self.assertEqual(len(posted), 1)
        self.assertEqual(posted[0].room, room)
        self.assertEqual(posted[0].cleaned, 1)
        self.assertEqual(posted[0].building, building)

        record.cancel()
        self.assertEqual(
            frappe.db.get_value("Cleaning Compliance Ledger", posted[0].name, "is_cancelled"),
            1,
            "the original ledger row must be flagged cancelled, never deleted",
        )
        reversal = frappe.db.get_value(
            "Cleaning Compliance Ledger", {"reversal_of": posted[0].name}, ["cleaned", "is_cancelled"]
        )
        self.assertEqual(
            reversal,
            (0, 1),
            "the reversal row must zero the cleaned fact and itself be flagged cancelled",
        )
