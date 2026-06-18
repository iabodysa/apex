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

# Controller hooks under test; the test is vacuous if these are not actually wired.
_MOVEMENT_HOOKS = ("on_submit", "on_cancel")


class TestFacilityAssetMovementEffects(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        # Per-test unique fixtures keyed off the method name; both buildings and
        # rooms autoname off a `field:` so names must not collide across tests.
        tag = self._testMethodName
        self.bldg_a = frappe.get_doc(
            {"doctype": "Accommodation Building", "building_name": f"FAM-EFFECTS A {tag}"}
        ).insert(ignore_permissions=True).name
        self.bldg_b = frappe.get_doc(
            {"doctype": "Accommodation Building", "building_name": f"FAM-EFFECTS B {tag}"}
        ).insert(ignore_permissions=True).name
        # to_room/from_room are real Accommodation Room links; their NAME (room_number)
        # is what on_submit copies into the asset's Data location field.
        self.room_l0 = frappe.get_doc(
            {
                "doctype": "Accommodation Room",
                "building": self.bldg_a,
                "room_number": f"FAM-EFFECTS L0 {tag}",
            }
        ).insert(ignore_permissions=True).name
        self.room_l1 = frappe.get_doc(
            {
                "doctype": "Accommodation Room",
                "building": self.bldg_b,
                "room_number": f"FAM-EFFECTS L1 {tag}",
            }
        ).insert(ignore_permissions=True).name
        # Asset starts at building A / location L0 with no movement history.
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

        # Non-vacuous guard 1: the seed really landed where the rest of the test assumes.
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
        # A -> B (L0 -> L1), same company so the intercompany gate stays off.
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
        # Non-vacuous guard 2: the side-effect hooks must actually be wired, else
        # doc.submit() would be a no-op and the asserts below would be meaningless.
        import apex_habitat.hooks as hooks

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
        # before_cancel requires a cancellation reason (allow_on_submit field).
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
