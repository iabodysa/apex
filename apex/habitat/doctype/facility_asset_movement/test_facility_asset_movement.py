# Copyright (c) 2026, afmcoltd
"""What Facility Asset Movement guarantees, asserted against the DocType itself.

Patterned on ``frappe/tests/test_document.py`` — the subject is ``validate``,
``on_submit``, ``before_cancel``, ``on_cancel`` and the whitelisted
``acknowledge_intercompany_movement``. ``validate`` reconciles a blank origin from the
asset's real location, refuses a hand-entered origin that contradicts it, refuses a
move to the same place, and refuses an intercompany move missing its approval gates.
``on_submit`` is the only thing that actually relocates the asset, snapshotting its
prior location first; ``before_cancel`` refuses to unwind a movement the asset has
since moved on from (last-in-first-out), and ``on_cancel`` restores the asset to where
this movement's own ledger row says it came from.

"Facility Asset" is deliberately absent from ``test_dependencies``: its own dependency
graph reaches Asset -> Journal Entry -> ... -> Payment Gateway, a DocType this bench
does not have installed. Every asset and building this test needs is built directly
below.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import getdate, today

from apex.habitat.doctype.facility_asset_movement.facility_asset_movement import (
    acknowledge_intercompany_movement,
)

test_dependencies = ["Building", "Room"]


def _fresh_building(company=None):
    building = frappe.copy_doc(frappe.get_test_records("Building")[0])
    building.building_name = f"_T-Movement Building {frappe.generate_hash(length=8)}"
    building.floor_plan = []
    if company:
        building.company = company
    building.insert()
    room = frappe.get_doc(
        {
            "doctype": "Room",
            "building": building.name,
            "room_number": f"_T-Movement-Room-{frappe.generate_hash(length=6)}",
        }
    ).insert()
    return building.name, room.name


def _fresh_asset(building, room):
    asset = frappe.copy_doc(frappe.get_test_records("Facility Asset")[0])
    asset.asset_name = f"_T-Movement Asset {frappe.generate_hash(length=6)}"
    asset.building = building
    asset.location_in_building = room
    asset.insert()
    return asset.name


def _new_movement(asset, to_building, to_room, **overrides):
    record = frappe.copy_doc(frappe.get_test_records("Facility Asset Movement")[0])
    record.facility_asset = asset
    record.from_building = None
    record.from_room = None
    record.to_building = to_building
    record.to_room = to_room
    for field, value in overrides.items():
        record.set(field, value)
    return record


class TestFacilityAssetMovement(FrappeTestCase):
    def test_a_move_to_the_same_location_is_refused(self):
        """A movement that goes nowhere is not a relocation."""
        building, room = _fresh_building()
        asset = _fresh_asset(building, room)

        record = _new_movement(asset, building, room)
        with self.assertRaisesRegex(frappe.ValidationError, "must differ"):
            record.insert()

    def test_a_hand_entered_origin_that_contradicts_the_assets_location_is_refused(self):
        """The origin cannot be hand-entered to a building the asset is not actually in."""
        building, room = _fresh_building()
        other_building, _other_room = _fresh_building()
        asset = _fresh_asset(building, room)

        record = _new_movement(asset, other_building, room, from_building=other_building)
        with self.assertRaisesRegex(frappe.ValidationError, "does not match the asset"):
            record.insert()

    def test_submit_relocates_the_asset_and_cancel_restores_its_prior_location(self):
        """The acceptance case, both directions: submit moves the asset, cancel undoes it."""
        origin_building, origin_room = _fresh_building()
        dest_building, dest_room = _fresh_building()
        asset = _fresh_asset(origin_building, origin_room)

        record = _new_movement(asset, dest_building, dest_room)
        record.insert()
        record.submit()

        moved = frappe.get_doc("Facility Asset", asset)
        self.assertEqual(moved.building, dest_building)
        self.assertEqual(moved.location_in_building, dest_room)
        self.assertEqual(moved.previous_building, origin_building)
        self.assertEqual(moved.previous_location_in_building, origin_room)
        self.assertEqual(moved.movement_count, 1)
        self.assertEqual(getdate(moved.last_movement_date), getdate(today()))

        with self.assertRaisesRegex(frappe.ValidationError, "Cancellation Reason is required"):
            record.cancel()

        record.reload()
        record.cancellation_reason = "Recorded in error"
        record.cancel()

        restored = frappe.get_doc("Facility Asset", asset)
        self.assertEqual(restored.building, origin_building)
        self.assertEqual(restored.location_in_building, origin_room)
        self.assertEqual(restored.movement_count, 0)
        self.assertIsNone(
            restored.previous_building,
            "cancelling the asset's only move must clear the audit trail it left",
        )
        self.assertIsNone(restored.last_movement_date)

    def test_cancel_is_refused_once_the_asset_has_moved_on_again(self):
        """Cancelling must be last-in-first-out: undo the newest relocation first."""
        first_building, first_room = _fresh_building()
        second_building, second_room = _fresh_building()
        third_building, third_room = _fresh_building()
        asset = _fresh_asset(first_building, first_room)

        first_move = _new_movement(asset, second_building, second_room)
        first_move.insert()
        first_move.submit()

        second_move = _new_movement(asset, third_building, third_room)
        second_move.insert()
        second_move.submit()

        first_move.cancellation_reason = "Attempting an out-of-order cancel"
        with self.assertRaisesRegex(frappe.ValidationError, "moved on"):
            first_move.cancel()

    def test_intercompany_gates_are_enforced_on_save(self):
        """An intercompany move needs both approvals at save time, and Permanent needs
        an accounting acknowledgement on top of them."""
        home_building, home_room = _fresh_building(company="_Test Company")
        foreign_building, foreign_room = _fresh_building(company="_Test Company 1")
        asset = _fresh_asset(home_building, home_room)

        missing_approvals = _new_movement(
            asset,
            foreign_building,
            foreign_room,
            release_approved_by=None,
            receiving_confirmed_by=None,
        )
        with self.assertRaisesRegex(frappe.ValidationError, "Release Approved By is required"):
            missing_approvals.insert()

        approved = _new_movement(
            asset,
            foreign_building,
            foreign_room,
            release_approved_by="Administrator",
            receiving_confirmed_by="test2@example.com",
        )
        approved.insert()
        self.assertTrue(approved.is_intercompany)

        permanent = _new_movement(
            asset,
            foreign_building,
            foreign_room,
            movement_category="Intercompany Permanent",
            release_approved_by="Administrator",
            receiving_confirmed_by="test2@example.com",
        )
        with self.assertRaisesRegex(frappe.ValidationError, "Accounting Acknowledged is required"):
            permanent.insert()

    def test_acknowledge_intercompany_movement_is_refused_in_each_wrong_state(self):
        """Draft, non-intercompany, and self-submitted are each refused for their own reason."""
        home_building, home_room = _fresh_building(company="_Test Company")
        foreign_building, foreign_room = _fresh_building(company="_Test Company 1")

        draft_asset = _fresh_asset(home_building, home_room)
        draft = _new_movement(
            draft_asset,
            foreign_building,
            foreign_room,
            release_approved_by="Administrator",
            receiving_confirmed_by="test2@example.com",
        )
        draft.insert()
        with self.assertRaisesRegex(frappe.ValidationError, "Only a submitted movement"):
            acknowledge_intercompany_movement(draft.name)

        same_company_asset = _fresh_asset(home_building, home_room)
        other_home_building, other_home_room = _fresh_building(company="_Test Company")
        same_company_move = _new_movement(same_company_asset, other_home_building, other_home_room)
        same_company_move.insert()
        same_company_move.submit()
        with self.assertRaisesRegex(frappe.ValidationError, "Only an intercompany movement"):
            acknowledge_intercompany_movement(same_company_move.name)

        intercompany_asset = _fresh_asset(home_building, home_room)
        intercompany_move = _new_movement(
            intercompany_asset,
            foreign_building,
            foreign_room,
            release_approved_by="Administrator",
            receiving_confirmed_by="test2@example.com",
        )
        intercompany_move.insert()
        intercompany_move.submit()
        with self.assertRaisesRegex(frappe.PermissionError, "cannot acknowledge it yourself"):
            acknowledge_intercompany_movement(intercompany_move.name)
