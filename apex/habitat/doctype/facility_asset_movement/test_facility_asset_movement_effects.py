# Copyright (c) 2026, AFMCO and contributors
"""Facility Asset Movement submittable side-effects (on_submit relocate / on_cancel revert).

Guards a bug already shipped once: on_submit wrote to nonexistent
current_building/current_room on Facility Asset, so every movement was a silent
no-op and the audit fields (building/location_in_building/previous_*/movement_count)
never moved. The existing controller test only covers insert / mandatory /
same-from-to / intercompany-gate validation and has ZERO references to
movement_count or previous_building. This proves the physical relocation and its
reversal end-to-end through doc.submit()/doc.cancel() so a re-regression to a
no-op (or a wrong fieldname) fails CI instead of leaving assets eternally parked
at their original location.

Verified against the DocType JSON before writing (do NOT guess fields):
- Facility Asset: building (Link Accommodation Building, reqd), location_in_building
  (Data), previous_building (Link), previous_location_in_building (Data),
  movement_count (Int), asset_category Select includes "CCTV Camera",
  responsible_supervisor (Link User, reqd).
- Facility Asset Movement: from_building/to_building (Link Accommodation Building),
  from_room/to_room (Link Accommodation Room), movement_category default
  "Same-Company Relocation", cancellation_reason required by before_cancel.
- on_submit snapshots the asset's CURRENT building/location into previous_*, so the
  seeded asset location must equal the movement's from_* for the A->A revert to hold.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today

# [#ju3nqz]
_MOVEMENT_HOOKS = ("on_submit", "on_cancel")


class TestFacilityAssetMovementEffects(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        # [#jvn7sf]
        tag = self._testMethodName
        self.bldg_a = frappe.get_doc(
            {"doctype": "Building", "building_name": f"FAM-EFFECTS A {tag}"}
        ).insert(ignore_permissions=True).name
        self.bldg_b = frappe.get_doc(
            {"doctype": "Building", "building_name": f"FAM-EFFECTS B {tag}"}
        ).insert(ignore_permissions=True).name
        # [#qc2tsa]
        self.room_l0 = frappe.get_doc(
            {
                "doctype": "Room",
                "building": self.bldg_a,
                "room_number": f"FAM-EFFECTS L0 {tag}",
            }
        ).insert(ignore_permissions=True).name
        self.room_l1 = frappe.get_doc(
            {
                "doctype": "Room",
                "building": self.bldg_b,
                "room_number": f"FAM-EFFECTS L1 {tag}",
            }
        ).insert(ignore_permissions=True).name
        # [#m6fk9q]
        self.asset = frappe.get_doc(
            {
                "doctype": "Facility Asset",
                "asset_name": f"FAM-EFFECTS Asset {tag}",
                "asset_category": "CCTV Camera",
                "building": self.bldg_a,
                "location_in_building": self.room_l0,
                "responsible_supervisor": "Administrator",
            }
        ).insert(ignore_permissions=True).name

        # [#bxh7g8]
        seeded = frappe.db.get_value(
            "Facility Asset",
            self.asset,
            ["building", "location_in_building", "movement_count"],
            as_dict=True,
        )
        self.assertEqual(seeded.building, self.bldg_a, "seed asset must start at building A")
        self.assertEqual(seeded.location_in_building, self.room_l0, "seed asset must start at L0")
        self.assertEqual((seeded.movement_count or 0), 0, "seed asset must have no movements yet")

    def tearDown(self):
        frappe.set_user("Administrator")

    def _movement(self):
        # [#4gy687]
        return frappe.get_doc(
            {
                "doctype": "Facility Asset Movement",
                "movement_date": today(),
                "facility_asset": self.asset,
                "movement_category": "Same-Company Relocation",
                "from_building": self.bldg_a,
                "from_room": self.room_l0,
                "to_building": self.bldg_b,
                "to_room": self.room_l1,
            }
        ).insert(ignore_permissions=True)

    def test_submit_relocates_asset_and_bumps_audit(self):
        # [#azktou]
        import apex.hooks as hooks

        wired = hooks.doc_events.get("Facility Asset Movement", {})
        for hook in _MOVEMENT_HOOKS:
            self.assertIn(hook, wired, f"Facility Asset Movement must wire {hook}")

        mv = self._movement()
        mv.submit()

        asset = frappe.db.get_value(
            "Facility Asset",
            self.asset,
            [
                "building",
                "location_in_building",
                "previous_building",
                "previous_location_in_building",
                "movement_count",
            ],
            as_dict=True,
        )
        self.assertEqual(asset.building, self.bldg_b, "submit must move the asset to building B")
        self.assertEqual(
            asset.location_in_building, self.room_l1, "submit must move the asset to L1"
        )
        self.assertEqual(
            asset.previous_building, self.bldg_a, "submit must snapshot the prior building A"
        )
        self.assertEqual(
            asset.previous_location_in_building,
            self.room_l0,
            "submit must snapshot the prior location L0",
        )
        self.assertEqual(asset.movement_count, 1, "submit must bump movement_count to 1")

    def test_cancel_reverts_asset_to_origin(self):
        mv = self._movement()
        mv.submit()
        # [#7k1vp7]
        mv.db_set("cancellation_reason", "Movement reversed in test")
        mv.reload()
        mv.cancel()

        asset = frappe.db.get_value(
            "Facility Asset",
            self.asset,
            ["building", "location_in_building", "movement_count"],
            as_dict=True,
        )
        self.assertEqual(asset.building, self.bldg_a, "cancel must revert the asset to building A")
        self.assertEqual(
            asset.location_in_building, self.room_l0, "cancel must revert the asset to L0"
        )
        self.assertEqual(asset.movement_count, 0, "cancel must decrement movement_count back to 0")

    _AUDIT_TRAIL = (
        "previous_building",
        "previous_location_in_building",
        "last_movement_date",
    )

    def _audit_trail(self):
        return frappe.db.get_value(
            "Facility Asset", self.asset, list(self._AUDIT_TRAIL), as_dict=True
        )

    def test_cancel_clears_the_audit_trail_of_the_movement_it_undid(self):
        """previous_*/last_movement_date are on_submit snapshots that no on_cancel
        reset, so reverting the only movement on a fresh asset left it reading "at A,
        previously A" and still stamped with the date of a move that no longer
        exists. The audit PAIR must survive or vanish together with the movement it
        describes."""
        before = self._audit_trail()
        # A never-moved asset carries no trail; that is the value cancel must return to.
        self.assertFalse(before.previous_building, "seed asset must carry no previous building")
        self.assertFalse(before.last_movement_date, "seed asset must carry no movement date")

        mv = self._movement()
        mv.submit()
        stamped = self._audit_trail()
        self.assertEqual(
            stamped.previous_building, self.bldg_a, "submit must stamp the prior building"
        )
        self.assertTrue(stamped.last_movement_date, "submit must stamp the movement date")

        mv.db_set("cancellation_reason", "Movement reversed in test")
        mv.reload()
        mv.cancel()

        after = self._audit_trail()
        for field in self._AUDIT_TRAIL:
            # NULL and "" both read as blank; compare on that axis, not on identity.
            self.assertEqual(
                after.get(field) or None,
                before.get(field) or None,
                f"cancel must return {field} to its pre-submit value",
            )
        self.assertNotEqual(
            after.previous_building,
            self.bldg_a,
            "an asset back at A must not also claim it was previously at A",
        )

    # An out-of-order cancel used to restore from_* blindly, dragging an asset that had
    # already moved on back to a building it had physically left.

    def _second_leg(self):
        """Building C + room L2, and a SUBMITTED second movement B -> C on the same
        asset. Returns (bldg_c, room_l2, movement)."""
        tag = self._testMethodName
        bldg_c = frappe.get_doc(
            {"doctype": "Building", "building_name": f"FAM-EFFECTS C {tag}"}
        ).insert(ignore_permissions=True).name
        room_l2 = frappe.get_doc(
            {"doctype": "Room", "building": bldg_c, "room_number": f"FAM-EFFECTS L2 {tag}"}
        ).insert(ignore_permissions=True).name
        mv2 = frappe.get_doc(
            {
                "doctype": "Facility Asset Movement",
                "movement_date": today(),
                "facility_asset": self.asset,
                "movement_category": "Same-Company Relocation",
                "from_building": self.bldg_b,
                "from_room": self.room_l1,
                "to_building": bldg_c,
                "to_room": room_l2,
            }
        ).insert(ignore_permissions=True)
        mv2.submit()
        return bldg_c, room_l2, mv2

    def test_cancelling_a_superseded_movement_cannot_drag_the_asset_back(self):
        mv1 = self._movement()
        mv1.submit()
        bldg_c, room_l2, _mv2 = self._second_leg()
        self.assertEqual(
            frappe.db.get_value("Facility Asset", self.asset, "building"),
            bldg_c,
            "the second movement must have left the asset at C",
        )

        mv1.db_set("cancellation_reason", "Out-of-order cancel attempt")
        mv1.reload()
        with self.assertRaises(frappe.ValidationError) as caught:
            mv1.cancel()
        # Every framework pre-cancel check subclasses ValidationError too, so a bare
        # assertRaises would pass on a link or timestamp failure instead of the guard.
        self.assertNotIsInstance(
            caught.exception,
            (frappe.LinkValidationError, frappe.TimestampMismatchError),
            "the refusal must come from the ordering guard, not a framework pre-cancel check",
        )

        asset = frappe.db.get_value(
            "Facility Asset",
            self.asset,
            ["building", "location_in_building", "movement_count"],
            as_dict=True,
        )
        self.assertEqual(
            asset.building, bldg_c, "a superseded cancel must leave the asset at C"
        )
        self.assertNotEqual(
            asset.building, self.bldg_a, "the asset must never be dragged back to A"
        )
        self.assertEqual(asset.location_in_building, room_l2, "the room must stay at L2")
        self.assertEqual(asset.movement_count, 2, "a refused cancel must not decrement the count")
        self.assertEqual(
            frappe.db.get_value("Facility Asset Movement", mv1.name, "docstatus"),
            1,
            "a refused cancel must leave the first movement submitted",
        )

    def test_cancelling_newest_first_walks_the_asset_back_leg_by_leg(self):
        """The remedy the refusal message names must actually work, or the guard is
        a dead end rather than an ordering rule."""
        mv1 = self._movement()
        mv1.submit()
        _bldg_c, _room_l2, mv2 = self._second_leg()

        for mv in (mv2, mv1):
            mv.db_set("cancellation_reason", "Reversed newest first in test")
            mv.reload()
            mv.cancel()

        asset = frappe.db.get_value(
            "Facility Asset",
            self.asset,
            ["building", "location_in_building", "movement_count"],
            as_dict=True,
        )
        self.assertEqual(asset.building, self.bldg_a, "last-in-first-out must land back at A")
        self.assertEqual(asset.location_in_building, self.room_l0, "and back at L0")
        self.assertEqual(asset.movement_count, 0, "both cancels must decrement the count")
