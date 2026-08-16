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

Three further classes below share this module for the same reason they used to share a
file with each other: each grades one more controller-level behaviour of Facility Asset
Movement (basic validate rules, the from_building origin-reconcile guard, and the ledger's
immutability/idempotency) through a real insert, each against its own small fixture rather
than this module's shared ``setUp``. ``TestFacilityAssetMovementLedger`` deliberately
excludes the two properties ``test_facility_asset_movement_reachability.py`` already covers
more strictly (see its own docstring) — duplicating the weaker versions here would only mean
a change to the ledger contract has to be made twice.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today

test_ignore = [
    "Additional Salary",
    "Asset",
    "Asset Movement",
    "Company",
    "Cost Center",
    "Currency",
    "Employee",
    "Item",
    "Payment Entry",
    "Project",
    "Purchase Invoice",
    "Role",
    "Salary Component",
    "Supplier",
    "User",
]

_MOVEMENT_HOOKS = ("on_submit", "on_cancel")


class TestFacilityAssetMovementEffects(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        tag = self._testMethodName
        self.bldg_a = frappe.get_doc(
            {"doctype": "Building", "building_name": f"FAM-EFFECTS A {tag}"}
        ).insert(ignore_permissions=True).name
        self.bldg_b = frappe.get_doc(
            {"doctype": "Building", "building_name": f"FAM-EFFECTS B {tag}"}
        ).insert(ignore_permissions=True).name
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

    # A delivered room that is not a Room record must survive the next movement, not be erased.

    FREE_TEXT_ROOM = "Storage Annex B"

    def test_movement_round_trip_preserves_a_room_that_is_not_a_room_record(self):
        """An asset parked in a free-text room survives submit + cancel.

        Facility Asset Delivery.to_location_in_building is Data and Facility Asset
        .location_in_building is Data, but the movement's from_room/to_room are Link
        Room. So a delivery can park an asset in a room string that is not a Room
        record. _reconcile_origin narrows that to the Link and leaves from_room blank,
        which is unavoidable; what was NOT unavoidable is that on_submit then ledgered
        the blank as the origin and on_cancel restored the blank onto the asset --
        erasing the only record of where the asset came from, with no warning.

        The ledger's from_location is Data, so it can hold the recorded room whatever
        its shape; the origin is kept there and read back on cancel, the same way
        Facility Asset Delivery.on_cancel already does through ledgered_origin.
        """
        # The state a delivery leaves behind: its destination room is Data, and
        # move_asset_on_delivery copies it verbatim onto the asset's Data room. Asserted
        # on the meta rather than staged through a whole 3-exit delivery, so this stays a
        # movement test -- but it is why a non-Room string can be there at all.
        for doctype, field in (
            ("Facility Asset Delivery", "to_location_in_building"),
            ("Facility Asset", "location_in_building"),
        ):
            self.assertEqual(
                frappe.get_meta(doctype).get_field(field).fieldtype,
                "Data",
                f"{doctype}.{field} must be free text for this scenario to be reachable",
            )
        frappe.db.set_value(
            "Facility Asset", self.asset, "location_in_building", self.FREE_TEXT_ROOM
        )
        self.assertFalse(
            frappe.db.exists("Room", self.FREE_TEXT_ROOM),
            "the fixture room must NOT be a Room record, or this proves nothing",
        )

        mv = frappe.get_doc(
            {
                "doctype": "Facility Asset Movement",
                "movement_date": today(),
                "facility_asset": self.asset,
                "movement_category": "Same-Company Relocation",
                "from_building": self.bldg_a,
                "to_building": self.bldg_b,
                "to_room": self.room_l1,
            }
        ).insert(ignore_permissions=True)
        self.assertFalse(
            mv.from_room, "a non-Room origin cannot go in the Link field; from_room stays blank"
        )
        mv.submit()

        # The room the asset actually left survives in the ledger, not in from_room.
        self.assertEqual(
            frappe.db.get_value(
                "Facility Asset Movement Ledger",
                {"source_doctype": mv.doctype, "source_name": mv.name, "reversal_of": ["is", "not set"]},
                "from_location",
            ),
            self.FREE_TEXT_ROOM,
            "the movement must ledger the room the asset really left, not the blank Link",
        )

        mv.db_set("cancellation_reason", "Movement reversed in test")
        mv.reload()
        mv.cancel()

        self.assertEqual(
            frappe.db.get_value("Facility Asset", self.asset, "location_in_building"),
            self.FREE_TEXT_ROOM,
            "cancel must put the asset back in the room it came from, not blank it",
        )

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
        """previous_*/last_movement_date are on_submit snapshots; on_cancel must reset
        them together with the location, or reverting the only movement on a fresh
        asset would read "at A, prior location also A" while still stamped with the
        date of a move that no longer exists. The audit PAIR must survive or vanish
        together with the movement it describes."""
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

    # An out-of-order cancel must not restore from_* blindly: that would drag an asset that has
    # already moved on back to a building it has physically left.

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


class TestFacilityAssetMovement(FrappeTestCase):
    """Basic validate()-level rules: mandatory fields, same-building refusal, and the
    intercompany flag being derived rather than settable."""

    def test_create_valid_movement(self):
        doc = frappe.get_doc({
            "doctype": "Facility Asset Movement",
            "naming_series": "FAM-.YYYY.-.####",
            "movement_date": "2026-06-01",
            "facility_asset": "FAC-AST-QA",
            "from_building": "BLDG-A",
            "to_building": "BLDG-B",
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.assertIsNotNone(doc.name)
        frappe.delete_doc("Facility Asset Movement", doc.name, force=True, ignore_permissions=True)

    def test_missing_facility_asset_raises(self):
        doc = frappe.get_doc({
            "doctype": "Facility Asset Movement",
            "naming_series": "FAM-.YYYY.-.####",
            "movement_date": "2026-06-01",
            "to_building": "BLDG-B",
        })
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert(ignore_permissions=True, ignore_links=True)

    def test_same_from_and_to_raises(self):
        from apex.habitat.doctype.facility_asset_movement.facility_asset_movement import validate

        doc = frappe.get_doc({
            "doctype": "Facility Asset Movement",
            "movement_date": "2026-06-01",
            "facility_asset": "FAC-AST-QA",
            "from_building": "BLDG-SAME",
            "to_building": "BLDG-SAME",
        })
        with self.assertRaises(frappe.ValidationError):
            validate(doc)

    def test_intercompany_detected_in_validate_enforces_gate(self):
        from apex.habitat.doctype.facility_asset_movement.facility_asset_movement import validate

        doc = frappe.get_doc({
            "doctype": "Facility Asset Movement",
            "movement_date": "2026-06-01",
            "facility_asset": "FAC-AST-QA",
            "from_building": "BLDG-A",
            "to_building": "BLDG-B",
            "from_company": "Company X",
            "to_company": "Company Y",
        })
        with self.assertRaises(frappe.ValidationError):
            validate(doc)
        self.assertEqual(doc.is_intercompany, 1)


class TestFacilityAssetMovementOriginReconcile(FrappeTestCase):
    """from_building/from_room are reconciled to the asset's actual location: a
    hand-entered origin that contradicts the asset is rejected, and a blank origin is
    defaulted from the asset so cancel reverts to a trustworthy prior location."""

    def _h(self):
        return frappe.generate_hash(length=12).upper()

    def _building(self, name):
        if not frappe.db.exists("Building", name):
            frappe.get_doc({
                "doctype": "Building", "building_name": name,
            }).insert(ignore_permissions=True, ignore_mandatory=True)
        return name

    def setUp(self):
        h = self._h()
        self.b1 = self._building("ORIG-A-" + h)
        self.b2 = self._building("ORIG-B-" + h)
        self.asset = frappe.get_doc({
            "doctype": "Facility Asset", "naming_series": "FAC-AST-.YYYY.-.####",
            "asset_name": "Origin-QA " + h, "asset_category": "Other", "building": self.b1,
        }).insert(ignore_permissions=True, ignore_mandatory=True).name

    def test_mismatched_from_building_rejected(self):
        """RED before fix: from_building was hand-entered and never checked, so a wrong
        origin slipped through (and on_cancel would later revert the asset to it). GREEN:
        validate throws when from_building contradicts the asset's current building."""
        from apex.habitat.doctype.facility_asset_movement.facility_asset_movement import validate

        doc = frappe.get_doc({
            "doctype": "Facility Asset Movement",
            "movement_date": "2026-06-01",
            "facility_asset": self.asset,
            "from_building": self.b2,
            "to_building": self.b1,
        })
        with self.assertRaises(frappe.ValidationError):
            validate(doc)

    def test_blank_origin_defaulted_and_cancel_restores_true_prior(self):
        """A blank from_building is defaulted from the asset, so after a move and a
        cancel the asset is restored to its genuine prior building (b1), not a phantom."""
        mv = frappe.get_doc({
            "doctype": "Facility Asset Movement",
            "naming_series": "FAM-.YYYY.-.####",
            "movement_date": "2026-06-01",
            "facility_asset": self.asset,
            "to_building": self.b2,
        })
        mv.insert(ignore_permissions=True, ignore_links=True)
        self.assertEqual(mv.from_building, self.b1)
        mv.submit()
        self.assertEqual(
            frappe.db.get_value("Facility Asset", self.asset, "building"), self.b2
        )
        mv.db_set("cancellation_reason", "QA origin test")
        mv.reload()
        mv.cancel()
        self.assertEqual(
            frappe.db.get_value("Facility Asset", self.asset, "building"), self.b1
        )


class TestFacilityAssetMovementLedger(FrappeTestCase):
    """The two ledger properties no OTHER module covers: a posted row cannot be edited,
    and re-posting the same movement does not post twice.

    ``test_submit_posts_one_immutable_from_to_row`` and ``test_cancel_posts_negated_reversal``
    are deliberately absent from this class: both are covered field-for-field and more strictly
    by ``test_facility_asset_movement_reachability`` — its
    ``test_submit_posts_exactly_one_ledger_effect`` counts the ledger GLOBALLY as well as per
    source (so a double post anywhere fails, which a count-by-source version could not
    catch), and its ``test_cancel_preserves_the_audit_trail`` asserts the original row
    survives unedited alongside exactly one reversal that points back at it. Duplicating the
    weaker versions here would only mean a change to the ledger contract has to be made twice.
    """

    LEDGER = "Facility Asset Movement Ledger"

    def _make_building(self, name):
        if not frappe.db.exists("Building", name):
            frappe.get_doc({
                "doctype": "Building",
                "building_name": name,
            }).insert(ignore_permissions=True, ignore_mandatory=True)
        return name

    def _make_asset(self, building):
        doc = frappe.get_doc({
            "doctype": "Facility Asset",
            "naming_series": "FAC-AST-.YYYY.-.####",
            "asset_name": "Ledger-QA-Asset",
            "asset_category": "Other",
            "building": building,
        }).insert(ignore_permissions=True, ignore_mandatory=True)
        return doc.name

    def _make_movement(self, asset, from_b, to_b):
        doc = frappe.get_doc({
            "doctype": "Facility Asset Movement",
            "naming_series": "FAM-.YYYY.-.####",
            "movement_date": "2026-06-01",
            "facility_asset": asset,
            "from_building": from_b,
            "to_building": to_b,
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        doc.submit()
        return doc

    def setUp(self):
        self.b1 = self._make_building("LEDGER-QA-A")
        self.b2 = self._make_building("LEDGER-QA-B")
        self.asset = self._make_asset(self.b1)

    def test_a_posted_row_cannot_be_edited(self):
        """Immutability is the whole reason the ledger is a separate record rather than a
        field on the asset. ``ignore_permissions=True`` is passed deliberately: the refusal
        must come from the ledger's own in_create/immutability guard and not from a DocPerm
        the caller happens to lack, so a bypass flag that silences it would fail here."""
        mv = self._make_movement(self.asset, self.b1, self.b2)
        rows = frappe.get_all(
            self.LEDGER,
            filters={"source_doctype": "Facility Asset Movement", "source_name": mv.name},
            fields=["name"],
        )
        self.assertEqual(len(rows), 1)

        led = frappe.get_doc(self.LEDGER, rows[0].name)
        led.to_location = "tampered"
        with self.assertRaises(frappe.PermissionError):
            led.save(ignore_permissions=True)

    def test_post_is_idempotent(self):
        from apex.habitat.asset_movement_engine import post_asset_movement

        mv = self._make_movement(self.asset, self.b1, self.b2)
        post_asset_movement(mv)
        rows = frappe.get_all(
            self.LEDGER,
            filters={
                "source_doctype": "Facility Asset Movement",
                "source_name": mv.name,
                "reversal_of": ["is", "not set"],
            },
        )
        self.assertEqual(len(rows), 1)
