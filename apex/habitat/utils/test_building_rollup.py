# Copyright (c) 2026, AFMCO and contributors
"""Direct coverage for ``apex.habitat.utils.building_rollup``.

The arithmetic (``annualized_rent``, ``total_annual_cost``, ``cost_per_capacity``)
takes plain numbers and needs no database. ``derive_total_capacity`` and
``distinct_floor_count`` read the building's real Room/Bed rows.

``derive_total_capacity`` is the module's own "live occupancy" rollup: it counts
only in-service, non-temporary Bed rows (excluding ``Out of Service`` and virtual
over-capacity beds), and it never queries Housing Assignment at all. The module
carries no assignment-cancellation logic of its own — that filter lives in
``occupancy.active_assignment_filters`` — so the boundary this file pins is that a
cancelled Housing Assignment leaves the underlying Bed row, and therefore this
rollup's count, untouched.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.habitat.utils import building_rollup
from apex.tests import factories


def _tag() -> str:
    """A collision-free identifier suffix, matching the suite-wide entropy floor."""
    return frappe.generate_hash(length=12)


class TestAnnualizedRent(FrappeTestCase):
    """Pure arithmetic — no database involved."""

    def test_annualized_rent_by_billing_cycle(self):
        """Each recognised billing cycle scales the rent to an annual figure."""
        self.assertEqual(building_rollup.annualized_rent(1000, "Monthly", None), 12000)
        self.assertEqual(building_rollup.annualized_rent(1000, "Quarterly", None), 4000)
        self.assertEqual(building_rollup.annualized_rent(1000, "Semi-Annual", None), 2000)
        self.assertEqual(building_rollup.annualized_rent(1000, "Annual", None), 1000)

    def test_an_unrecognised_billing_cycle_is_treated_as_already_annual(self):
        """An unknown cycle string falls back to a factor of one."""
        self.assertEqual(building_rollup.annualized_rent(1000, "Fortnightly", None), 1000)

    def test_company_share_narrows_the_annual_figure(self):
        """A set share percentage narrows the annualised rent to the company's cut."""
        self.assertEqual(building_rollup.annualized_rent(1000, "Monthly", 50), 6000)

    def test_a_zero_or_unset_share_means_the_whole_rent_is_owed(self):
        """A zero/unset share is not read as zero owed."""
        self.assertEqual(building_rollup.annualized_rent(1000, "Monthly", 0), 12000)
        self.assertEqual(building_rollup.annualized_rent(1000, "Monthly", None), 12000)


class TestTotalAnnualCostAndCostPerCapacity(FrappeTestCase):
    """Pure arithmetic — no database involved."""

    def test_total_annual_cost_sums_every_declared_cost_column(self):
        """Every column in ``ANNUAL_COST_FIELDS`` contributes to the total."""
        source = {field: 100 for field in building_rollup.ANNUAL_COST_FIELDS}
        self.assertEqual(
            building_rollup.total_annual_cost(source), 100 * len(building_rollup.ANNUAL_COST_FIELDS)
        )

    def test_total_annual_cost_treats_a_missing_column_as_zero(self):
        """A mapping missing a cost column contributes zero for it, not an error."""
        self.assertEqual(building_rollup.total_annual_cost({}), 0)

    def test_cost_per_capacity_with_zero_capacity_is_zero_not_a_division_error(self):
        """A building with no declared capacity costs nothing per head."""
        self.assertEqual(building_rollup.cost_per_capacity(1200, 0), (0, 0))
        self.assertEqual(building_rollup.cost_per_capacity(1200, None), (0, 0))

    def test_cost_per_capacity_divides_the_annual_total_into_annual_and_monthly(self):
        """The monthly figure is the annual figure divided by twelve."""
        annual, monthly = building_rollup.cost_per_capacity(1200, 10)
        self.assertEqual(annual, 120)
        self.assertEqual(monthly, 10)


class TestDistinctFloorCount(FrappeTestCase):
    """Reads the building's real Room rows."""

    def setUp(self):
        """Ensures the shared test company exists before any Building is built."""
        factories.make_company()

    def test_a_room_left_without_a_floor_counts_as_the_ground_floor(self):
        """An unset floor is stored as 0 and counted as Ground, because the schema says so.

        `Room.floor` is a Frappe `Int`, whose column is `int(11) NOT NULL DEFAULT 0`. A room
        saved without a floor therefore holds 0, which is the same value a genuine ground-floor
        room holds. This pins the honest behaviour rather than the impossible one: the function
        once filtered `f is not None` and promised to drop floorless rooms, a guard that could
        never fire under this column type.
        """
        building = factories.make_building(name=f"Rollup Floors {_tag()}")
        factories.make_room(building.name, room_number=f"{building.name}-F1", floor=1)
        factories.make_room(building.name, room_number=f"{building.name}-F2", floor=2)
        factories.make_room(building.name, room_number=f"{building.name}-FN")

        self.assertEqual(
            frappe.db.get_value("Room", f"{building.name}-FN", "floor"),
            0,
            "an unset Int floor is stored as 0, never NULL",
        )
        self.assertEqual(
            building_rollup.distinct_floor_count(building.name),
            3,
            "floors 1, 2 and the ground floor the floorless room sits on",
        )


class TestDeriveTotalCapacity(FrappeTestCase):
    """Reads the building's real Bed rows."""

    def setUp(self):
        """Ensures the shared test company exists before any Building is built."""
        factories.make_company()

    def test_none_before_any_bed_exists(self):
        """A pre-generation building keeps its manually-entered planned capacity,
        signalled by ``None`` rather than ``0``."""
        building = factories.make_building(name=f"Rollup NoBed {_tag()}")
        self.assertIsNone(building_rollup.derive_total_capacity(building.name))

    def test_excludes_out_of_service_and_temporary_beds(self):
        """Only a live, non-temporary bed counts toward total capacity."""
        building = factories.make_building(name=f"Rollup Capacity {_tag()}")
        room = factories.make_room(building.name, bed_capacity=3)
        live_bed = factories.make_bed(room.name, bed_code=f"{room.name}-B01")
        retired_bed = factories.make_bed(room.name, bed_code=f"{room.name}-B02")
        factories.make_bed(room.name, bed_code=f"{room.name}-B03", is_temporary=1)
        frappe.db.set_value("Bed", retired_bed.name, "status", "Out of Service")

        self.assertEqual(
            building_rollup.derive_total_capacity(building.name), 1,
            "only the live, non-temporary bed counts",
        )
        self.assertTrue(live_bed.name)

    def test_a_cancelled_housing_assignment_leaves_the_capacity_rollup_unchanged(self):
        """``derive_total_capacity`` reads Bed rows only — it never queries Housing
        Assignment — so a bed under a cancelled assignment stays counted exactly as
        it was before the assignment existed."""
        building = factories.make_building(name=f"Rollup Cancelled {_tag()}")
        room = factories.make_room(building.name, bed_capacity=1)
        bed = factories.make_bed(room.name)
        before = building_rollup.derive_total_capacity(building.name)

        employee = factories.make_employee(name=f"Rollup Worker {_tag()}")
        project = factories.make_project(f"Rollup Project {_tag()}")
        assignment_name = factories.make_assignment(
            employee.name, building.name, project, room_number=room.name, bed_code=bed.name,
        )
        frappe.get_doc("Housing Assignment", assignment_name).cancel()

        after = building_rollup.derive_total_capacity(building.name)
        self.assertEqual(
            before, after,
            "a cancelled assignment must not change what this rollup counts as live capacity",
        )
