# Copyright (c) 2026, afmcoltd
"""What Facility Asset Delivery guarantees, asserted against the DocType itself.

Patterned on ``frappe/tests/test_document.py`` — the subject is ``validate``,
``on_submit``, ``before_update_after_submit``, ``before_cancel`` and ``on_cancel``,
driven through the real 3-exit lock in ``habitat.api.facility_asset_delivery``
(``pass_exit_1``, ``pass_exit_3``, ``confirm_receipt``) rather than a raw status
assignment, because that lock is the real door a user pushes the delivery through.
``validate`` refuses a same-building "move", the same person on both sides of the
hand-over, and a hand-entered origin that contradicts the asset's real location. The
asset does not move until ``confirm_receipt`` succeeds; ``before_update_after_submit``
blocks a plain edit of any exit checkpoint field, since only the exit's own action may
clear it; ``on_cancel`` reverses the movement only when the asset actually moved.

"Facility Asset" is deliberately absent from ``test_dependencies``: its own dependency
graph reaches Asset -> Journal Entry -> ... -> Payment Gateway, a DocType this bench
does not have installed. Every asset and building this test needs is built directly
below.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.habitat.api.facility_asset_delivery import (
    confirm_receipt,
    pass_exit_1,
    pass_exit_3,
)

test_dependencies = ["Building", "Room"]


def _fresh_building():
    building = frappe.copy_doc(frappe.get_test_records("Building")[0])
    building.building_name = f"_T-Delivery Building {frappe.generate_hash(length=8)}"
    building.floor_plan = []
    building.insert()
    room = frappe.get_doc(
        {
            "doctype": "Room",
            "building": building.name,
            "room_number": f"_T-Delivery-Room-{frappe.generate_hash(length=6)}",
        }
    ).insert()
    return building.name, room.name


def _fresh_asset(building, room):
    asset = frappe.copy_doc(frappe.get_test_records("Facility Asset")[0])
    asset.asset_name = f"_T-Delivery Asset {frappe.generate_hash(length=6)}"
    asset.building = building
    asset.location_in_building = room
    asset.insert()
    return asset.name


def _new_delivery(asset, to_building, to_room, **overrides):
    record = frappe.copy_doc(frappe.get_test_records("Facility Asset Delivery")[0])
    record.facility_asset = asset
    record.from_building = None
    record.to_building = to_building
    record.to_location_in_building = to_room
    record.initiated_by = "test2@example.com"
    record.receiving_supervisor = "test3@example.com"
    for field, value in overrides.items():
        record.set(field, value)
    return record


class TestFacilityAssetDelivery(FrappeTestCase):
    def test_validate_refuses_a_same_building_move_and_a_shared_initiator_and_receiver(self):
        """Neither guard has anything to do with the exit lock; both fire on save."""
        building, room = _fresh_building()
        asset = _fresh_asset(building, room)

        same_building = _new_delivery(asset, building, room)
        with self.assertRaisesRegex(frappe.ValidationError, "must be different"):
            same_building.insert()

        other_building, other_room = _fresh_building()
        same_person = _new_delivery(
            asset,
            other_building,
            other_room,
            initiated_by="test2@example.com",
            receiving_supervisor="test2@example.com",
        )
        with self.assertRaisesRegex(frappe.ValidationError, "must be different people"):
            same_person.insert()

    def test_validate_refuses_a_hand_entered_origin_that_contradicts_the_asset(self):
        """The origin cannot be hand-entered to a building the asset is not actually in."""
        building, room = _fresh_building()
        wrong_building, _wrong_room = _fresh_building()
        dest_building, dest_room = _fresh_building()
        asset = _fresh_asset(building, room)

        record = _new_delivery(asset, dest_building, dest_room, from_building=wrong_building)
        with self.assertRaisesRegex(frappe.ValidationError, "does not match the asset"):
            record.insert()

    def test_the_full_lock_moves_the_asset_only_once_confirmed_and_locks_the_exit_fields(self):
        """The acceptance case: submit opens the lock, both exits release it, and only
        a confirmed on-site code actually relocates the asset."""
        origin_building, origin_room = _fresh_building()
        dest_building, dest_room = _fresh_building()
        asset = _fresh_asset(origin_building, origin_room)

        delivery = _new_delivery(asset, dest_building, dest_room)
        delivery.insert()
        delivery.submit()
        self.assertEqual(delivery.status, "Pending Exits")

        with self.assertRaisesRegex(
            frappe.PermissionError, "cleared by its own action"
        ):
            delivery.exit1_security_cleared = 1
            delivery.save()

        pass_exit_1(delivery.name)
        result = pass_exit_3(delivery.name)
        code = result["code"]
        self.assertIsNotNone(code)
        self.assertEqual(
            frappe.db.get_value("Facility Asset Delivery", delivery.name, "status"), "Released"
        )
        self.assertEqual(
            frappe.db.get_value("Facility Asset", asset, "building"),
            origin_building,
            "the asset must not move before the on-site code is confirmed",
        )

        confirm_receipt(delivery.name, code)

        self.assertEqual(
            frappe.db.get_value("Facility Asset Delivery", delivery.name, "status"), "Delivered"
        )
        moved = frappe.get_doc("Facility Asset", asset)
        self.assertEqual(moved.building, dest_building)
        self.assertEqual(moved.location_in_building, dest_room)

        record = frappe.get_doc("Facility Asset Delivery", delivery.name)
        record.cancellation_reason = "Delivered to the wrong destination"
        record.cancel()
        reverted = frappe.get_doc("Facility Asset", asset)
        self.assertEqual(
            reverted.building,
            origin_building,
            "cancelling a Delivered delivery must reverse the move it made",
        )

    def test_cancelling_before_delivery_never_moves_the_asset_and_requires_a_reason(self):
        """A delivery cancelled before Delivered never moved the asset, so unwinding it is a no-op."""
        origin_building, origin_room = _fresh_building()
        dest_building, dest_room = _fresh_building()
        asset = _fresh_asset(origin_building, origin_room)

        delivery = _new_delivery(asset, dest_building, dest_room)
        delivery.insert()
        delivery.submit()

        with self.assertRaisesRegex(frappe.ValidationError, "Cancellation Reason is required"):
            delivery.cancel()

        delivery.reload()
        delivery.cancellation_reason = "Delivery no longer needed"
        delivery.cancel()

        self.assertEqual(
            frappe.db.get_value("Facility Asset Delivery", delivery.name, "status"), "Cancelled"
        )
        self.assertEqual(
            frappe.db.get_value("Facility Asset", asset, "building"),
            origin_building,
            "an asset that never moved must still be exactly where it started",
        )
