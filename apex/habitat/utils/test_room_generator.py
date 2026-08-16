# Copyright (c) 2026, AFMCO and contributors
"""Direct coverage for ``apex.habitat.utils.room_generator``.

The Building controller's whitelisted ``generate_rooms_and_beds`` is exercised
end-to-end elsewhere (``building/test_idempotency_guards.py``); this module drives
the generator's own callables directly, without going through that whitelisted
entry point, so the naming, ordering, and reconciliation rules stay provable on
their own.

Pins three behaviours: a second generation run on an unchanged floor plan creates
nothing new; a generated room's bed count equals its ``bed_capacity``; a Basement
floor is placed below Ground both in its floor code and its sort order.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.habitat.utils import room_generator
from apex.tests import factories


def _tag() -> str:
    """A collision-free identifier suffix, matching the suite-wide entropy floor."""
    return frappe.generate_hash(length=12)


def _floor_row(**overrides) -> "frappe._dict":
    """A plain floor-plan row, shaped like a ``Floor Plan`` child table row."""
    row = frappe._dict(
        {
            "floor_number": 1,
            "floor_type": "Ground",
            "starting_room_number": 1,
            "room_count": 3,
            "bed_capacity_per_room": 2,
            "room_type": "Standard",
            "generate_beds": 1,
            "room_prefix": "",
        }
    )
    row.update(overrides)
    return row


class TestRoomNumberAndFloorCode(FrappeTestCase):
    """Pure naming/ordering rules — no database involved."""

    def test_room_number_blank_prefix_matches_historical_format(self):
        """A blank prefix yields ``{abbr}-{floor_code}{seq:02d}`` byte-for-byte."""
        self.assertEqual(room_generator.room_number("JED1", "G", "", 1), "JED1-G01")

    def test_room_number_with_prefix_adds_a_wing_segment(self):
        """A non-blank prefix only ADDS a segment; it never renumbers."""
        self.assertEqual(room_generator.room_number("JED1", "G", "A", 1), "JED1-GA01")

    def test_floor_code_basement_is_below_ground(self):
        """A Basement floor code carries a ``B`` marker distinct from Ground's ``G``."""
        self.assertEqual(room_generator.floor_code("Basement", 1), "B1")
        self.assertEqual(room_generator.floor_code("Basement", 0), "B")
        self.assertEqual(room_generator.floor_code("Ground", 0), "G")

    def test_floor_code_roof_and_middle(self):
        """A Roof floor above the first carries its number; a middle floor is numeric."""
        self.assertEqual(room_generator.floor_code("Roof", 1), "R")
        self.assertEqual(room_generator.floor_code("Roof", 2), "R2")
        self.assertEqual(room_generator.floor_code(None, 3), "3")

    def test_floor_sort_key_places_basement_below_ground_below_roof(self):
        """A Basement row's sort key is lower than Ground's, which is lower than a
        Middle floor's, which is lower than Roof's — bottom-to-top ordering."""
        basement = room_generator.floor_sort_key(_floor_row(floor_type="Basement", floor_number=1))
        ground = room_generator.floor_sort_key(_floor_row(floor_type="Ground", floor_number=0))
        middle = room_generator.floor_sort_key(_floor_row(floor_type=None, floor_number=2))
        roof = room_generator.floor_sort_key(_floor_row(floor_type="Roof", floor_number=1))
        self.assertLess(basement, ground, "a Basement floor must sort below Ground")
        self.assertLess(ground, middle)
        self.assertLess(middle, roof)


class TestValidateFloorPlan(FrappeTestCase):
    """``validate_floor_plan`` runs against a Building's in-memory ``floor_plan``
    rows; neither branch here needs the document saved."""

    def test_no_floor_rows_is_rejected(self):
        """An empty floor plan has nothing to generate from."""
        doc = frappe._dict(floor_plan=[])
        with self.assertRaises(frappe.ValidationError):
            room_generator.validate_floor_plan(doc)

    def test_two_floors_sharing_a_floor_code_is_rejected(self):
        """Two floors collapsing to the same floor code would mint identical room
        numbers, so the conflict is caught before any room is generated."""
        doc = frappe._dict(
            floor_plan=[
                _floor_row(floor_type="Basement", floor_number=1),
                _floor_row(floor_type="Basement", floor_number=1),
            ]
        )
        with self.assertRaises(frappe.ValidationError):
            room_generator.validate_floor_plan(doc)


class TestGenerationStatsShapedHelpers(FrappeTestCase):
    """``needs_confirmation`` / ``generation_summary`` / ``generation_message`` /
    ``generation_indicator`` all take a plain ``GenerationStats`` and read it back."""

    def test_needs_confirmation_true_when_anything_is_pending(self):
        """Any of the three pending counters alone is enough to require confirmation."""
        for field in ("pending_new_rooms", "pending_new_beds", "pending_capacity_reductions"):
            with self.subTest(field=field):
                stats = room_generator.GenerationStats()
                setattr(stats, field, 1)
                self.assertTrue(room_generator.needs_confirmation(stats))

    def test_needs_confirmation_false_when_nothing_is_pending(self):
        """A freshly zeroed tally needs no confirmation."""
        self.assertFalse(room_generator.needs_confirmation(room_generator.GenerationStats()))

    def test_generation_summary_carries_every_counter(self):
        """The machine-readable summary exposes every counter the caller reads."""
        stats = room_generator.GenerationStats()
        stats.created_rooms = 3
        stats.created_beds = 6
        summary = room_generator.generation_summary(stats)
        self.assertEqual(summary["created_rooms"], 3)
        self.assertEqual(summary["created_beds"], 6)
        self.assertFalse(summary["needs_confirmation"])
        self.assertEqual(summary["blocked_reductions"], [])

    def test_generation_message_pending_wording(self):
        """A run with pending creations reports what it did not yet create."""
        stats = room_generator.GenerationStats()
        stats.pending_new_rooms = 2
        stats.pending_new_beds = 4
        message = room_generator.generation_message(stats)
        self.assertIn("not yet created", message)

    def test_generation_message_complete_wording(self):
        """A run with nothing pending reports itself as complete."""
        stats = room_generator.GenerationStats()
        stats.created_rooms = 3
        message = room_generator.generation_message(stats)
        self.assertIn("Generation complete", message)

    def test_generation_indicator_green_when_clean_orange_when_pending_or_failed(self):
        """Green only when the run finished with nothing pending and nothing failed."""
        clean = room_generator.GenerationStats()
        self.assertEqual(room_generator.generation_indicator(clean), "green")

        pending = room_generator.GenerationStats()
        pending.pending_new_rooms = 1
        self.assertEqual(room_generator.generation_indicator(pending), "orange")

        failed = room_generator.GenerationStats()
        failed.row_failures.append("boom")
        self.assertEqual(room_generator.generation_indicator(failed), "orange")

    def test_report_generation_returns_the_summary_and_does_not_raise(self):
        """``report_generation`` msgprints the operator account and hands back the
        same dict ``generation_summary`` would."""
        stats = room_generator.GenerationStats()
        stats.created_rooms = 1
        result = room_generator.report_generation(stats)
        self.assertEqual(result, room_generator.generation_summary(stats))


class TestGenerateAndRegenerate(FrappeTestCase):
    """The core generation flow: create, re-run, and reduce a real building's rooms
    and beds through ``process_floor_row`` directly."""

    def setUp(self):
        """Ensures the shared test company exists before any Building is built."""
        factories.make_company()

    def test_first_run_creates_rooms_with_beds_matching_bed_capacity(self):
        """A first generation creates every planned room, and each room's bed count
        equals its ``bed_capacity``."""
        tag = _tag()
        building = factories.make_building(name=f"Room Generator {tag}", abbreviation=f"RG{tag}")
        existing_room_map, existing_bed_codes = room_generator.load_existing(building.name)
        self.assertEqual(existing_room_map, {}, "a fresh building starts with no known rooms")

        row = _floor_row()
        stats = room_generator.GenerationStats()
        room_generator.process_floor_row(
            row, building.abbreviation, building.name, True, True,
            existing_room_map, existing_bed_codes, stats,
        )

        self.assertEqual(stats.created_rooms, 3)
        self.assertEqual(stats.created_beds, 6)

        room_names = frappe.get_all("Room", filters={"building": building.name}, pluck="name")
        self.assertEqual(len(room_names), 3)
        for room_name in room_names:
            capacity = frappe.db.get_value("Room", room_name, "bed_capacity")
            bed_count = frappe.db.count("Bed", {"room": room_name})
            self.assertEqual(
                bed_count, capacity,
                f"{room_name}: bed count must equal its own bed_capacity",
            )

    def test_second_run_on_an_unchanged_plan_creates_nothing(self):
        """Generating rooms for a building twice creates none the second time."""
        tag = _tag()
        building = factories.make_building(name=f"Room Generator Rerun {tag}", abbreviation=f"RR{tag}")
        row = _floor_row()

        first_map, first_beds = room_generator.load_existing(building.name)
        first_stats = room_generator.GenerationStats()
        room_generator.process_floor_row(
            row, building.abbreviation, building.name, True, True,
            first_map, first_beds, first_stats,
        )
        rooms_after_first = frappe.db.count("Room", {"building": building.name})
        beds_after_first = frappe.db.count(
            "Bed", {"room": ["in", frappe.get_all("Room", {"building": building.name}, pluck="name")]}
        )

        second_map, second_beds = room_generator.load_existing(building.name)
        second_stats = room_generator.GenerationStats()
        room_generator.process_floor_row(
            row, building.abbreviation, building.name, True, True,
            second_map, second_beds, second_stats,
        )

        self.assertEqual(second_stats.created_rooms, 0, "a second run must create no new rooms")
        self.assertEqual(second_stats.created_beds, 0, "a second run must create no new beds")
        self.assertEqual(second_stats.skipped_rooms, 3)

        rooms_after_second = frappe.db.count("Room", {"building": building.name})
        beds_after_second = frappe.db.count(
            "Bed", {"room": ["in", frappe.get_all("Room", {"building": building.name}, pluck="name")]}
        )
        self.assertEqual(rooms_after_second, rooms_after_first)
        self.assertEqual(beds_after_second, beds_after_first)

    def test_run_without_allow_create_reports_pending_and_creates_nothing(self):
        """When creation is not yet permitted, new rooms are counted pending, not made."""
        tag = _tag()
        building = factories.make_building(name=f"Room Generator Pending {tag}", abbreviation=f"RP{tag}")
        row = _floor_row()
        existing_map, existing_beds = room_generator.load_existing(building.name)
        stats = room_generator.GenerationStats()

        room_generator.process_floor_row(
            row, building.abbreviation, building.name, False, True,
            existing_map, existing_beds, stats,
        )

        self.assertEqual(stats.created_rooms, 0)
        self.assertEqual(stats.pending_new_rooms, 3)
        self.assertTrue(room_generator.needs_confirmation(stats))
        self.assertEqual(frappe.db.count("Room", {"building": building.name}), 0)

    def test_confirmed_capacity_reduction_retires_the_surplus_bed(self):
        """A confirmed capacity decrease retires the surplus bed (Out of Service) and
        lowers ``bed_capacity``; this exercises the reconciliation and reduction path."""
        tag = _tag()
        building = factories.make_building(name=f"Room Generator Reduce {tag}", abbreviation=f"RD{tag}")
        grow_row = _floor_row(room_count=1, bed_capacity_per_room=2)

        existing_map, existing_beds = room_generator.load_existing(building.name)
        room_generator.process_floor_row(
            grow_row, building.abbreviation, building.name, True, True,
            existing_map, existing_beds, room_generator.GenerationStats(),
        )
        room_name = frappe.get_all("Room", {"building": building.name}, pluck="name")[0]

        shrink_row = _floor_row(room_count=1, bed_capacity_per_room=1)
        reduce_map, reduce_beds = room_generator.load_existing(building.name)
        reduce_stats = room_generator.GenerationStats()
        room_generator.process_floor_row(
            shrink_row, building.abbreviation, building.name, True, True,
            reduce_map, reduce_beds, reduce_stats,
        )

        self.assertEqual(reduce_stats.retired_beds, 1)
        self.assertEqual(reduce_stats.updated_rooms, 1)
        self.assertEqual(reduce_stats.blocked_reductions, [])
        self.assertEqual(frappe.db.get_value("Room", room_name, "bed_capacity"), 1)
        self.assertEqual(
            frappe.db.get_value("Bed", f"{room_name}-B02", "status"), "Out of Service",
        )

    def test_finalize_building_stats_updates_setup_status_and_totals(self):
        """After a write, the building's setup status and derived totals refresh."""
        tag = _tag()
        building = factories.make_building(name=f"Room Generator Finalize {tag}", abbreviation=f"RF{tag}")
        row = _floor_row()
        existing_map, existing_beds = room_generator.load_existing(building.name)
        stats = room_generator.GenerationStats()
        room_generator.process_floor_row(
            row, building.abbreviation, building.name, True, True,
            existing_map, existing_beds, stats,
        )

        room_generator.finalize_building_stats(building.name, stats)

        refreshed = frappe.db.get_value(
            "Building", building.name,
            ["setup_status", "total_rooms", "total_capacity"], as_dict=True,
        )
        self.assertEqual(refreshed.setup_status, "Rooms Generated")
        self.assertEqual(refreshed.total_rooms, 3)
        self.assertEqual(refreshed.total_capacity, 6)

    def test_finalize_building_stats_is_a_no_op_when_nothing_was_written(self):
        """A stats object with no writes leaves the building's setup status alone."""
        tag = _tag()
        building = factories.make_building(name=f"Room Generator Noop {tag}", abbreviation=f"RN{tag}")
        room_generator.finalize_building_stats(building.name, room_generator.GenerationStats())
        self.assertEqual(frappe.db.get_value("Building", building.name, "setup_status"), "Draft")
