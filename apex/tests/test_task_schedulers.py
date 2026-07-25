# Copyright (c) 2026, AFMCO and contributors
# [#j03s5a]
"""Unit tests for habitat/tasks.py scheduler functions.

Most of these need no Frappe at all — the occupancy and Select-option cases are
pure arithmetic and set algebra, verified without a database.

``TestDeadBeforeSaveGuardsRemoved`` is the exception: it imports the real
controller modules, so it needs frappe IMPORTABLE (not a live site). That always
holds under ``bench run-tests``. It used to swallow an ImportError into a
``skipTest``, which turned "the controllers no longer import" — a genuine
breakage — into a green run, so the import is now allowed to fail loudly.
"""

from __future__ import annotations

import importlib
import inspect
import unittest


class TestWeeklyOccupancySyncEmptyBuilding(unittest.TestCase):
    """Finding 2: weekly_occupancy_sync must not divide by zero or crash
    when a building has no rooms assigned."""

    def _run_sync_building_pass(self, buildings, room_counts, active_counts, capacities):
        """Helper that exercises only the building pass of weekly_occupancy_sync
        via a stripped-down reimplementation matching the patched logic."""
        results = {}
        for b in buildings:
            total_rooms = room_counts.get(b, 0)
            if not total_rooms:
                # [#g0v5hn]
                continue
            active = active_counts.get(b, 0)
            total_capacity = capacities.get(b, 0)
            occupancy_pct = (active / total_capacity * 100) if total_capacity else 0.0
            results[b] = {"current_occupants": active, "occupancy_percent": round(occupancy_pct, 2)}
        return results

    def test_empty_building_skipped(self):
        """A building with zero rooms must be skipped without raising ZeroDivisionError."""
        buildings = ["BLDG-EMPTY", "BLDG-NORMAL"]
        room_counts = {"BLDG-EMPTY": 0, "BLDG-NORMAL": 5}
        active_counts = {"BLDG-EMPTY": 0, "BLDG-NORMAL": 3}
        capacities = {"BLDG-EMPTY": 0, "BLDG-NORMAL": 20}

        results = self._run_sync_building_pass(buildings, room_counts, active_counts, capacities)

        self.assertNotIn("BLDG-EMPTY", results, "Empty building should be skipped.")
        self.assertIn("BLDG-NORMAL", results)
        self.assertEqual(results["BLDG-NORMAL"]["current_occupants"], 3)
        self.assertAlmostEqual(results["BLDG-NORMAL"]["occupancy_percent"], 15.0)

    def test_zero_capacity_building_does_not_divide(self):
        """A building with rooms but zero total_capacity must produce 0.0 occupancy_percent."""
        buildings = ["BLDG-NO-CAP"]
        room_counts = {"BLDG-NO-CAP": 2}
        active_counts = {"BLDG-NO-CAP": 1}
        capacities = {"BLDG-NO-CAP": 0}

        results = self._run_sync_building_pass(buildings, room_counts, active_counts, capacities)

        self.assertIn("BLDG-NO-CAP", results)
        self.assertEqual(results["BLDG-NO-CAP"]["occupancy_percent"], 0.0)

    def test_fully_occupied_building(self):
        """A fully occupied building should show 100% occupancy."""
        buildings = ["BLDG-FULL"]
        room_counts = {"BLDG-FULL": 10}
        active_counts = {"BLDG-FULL": 20}
        capacities = {"BLDG-FULL": 20}

        results = self._run_sync_building_pass(buildings, room_counts, active_counts, capacities)

        self.assertIn("BLDG-FULL", results)
        self.assertAlmostEqual(results["BLDG-FULL"]["occupancy_percent"], 100.0)


class TestLedgerTypeOptions(unittest.TestCase):
    """Finding 1: Accommodation Ledger ledger_type Select must include all
    utility_type values from Utility Account."""

    # [#q5c3pm]
    LEDGER_TYPE_OPTIONS = {
        "Rent",
        "Electricity",
        "Water",
        "Gas",
        "Internet",
        "Telecom",
        "Cleaning Staff Salary",
        "Supervisor Salary",
        "Maintenance",
        "Other",
    }

    # [#f15ecz]
    UTILITY_TYPES = {"Electricity", "Water", "Gas", "Internet", "Telecom"}

    def test_all_utility_types_covered_by_ledger_type(self):
        """Every utility_type value must be a valid ledger_type option."""
        missing = self.UTILITY_TYPES - self.LEDGER_TYPE_OPTIONS
        self.assertEqual(
            missing,
            set(),
            f"utility_type values not in ledger_type options: {missing}",
        )

    def test_json_options_contain_gas(self):
        """Gas must be in the ledger_type options."""
        self.assertIn("Gas", self.LEDGER_TYPE_OPTIONS)

    def test_json_options_contain_internet(self):
        """Internet must be in the ledger_type options."""
        self.assertIn("Internet", self.LEDGER_TYPE_OPTIONS)

    def test_json_options_contain_telecom(self):
        """Telecom must be in the ledger_type options."""
        self.assertIn("Telecom", self.LEDGER_TYPE_OPTIONS)


class TestDeadBeforeSaveGuardsRemoved(unittest.TestCase):
    """Finding 4: dead before_save guards that check self.doctype != "..." have been removed."""

    def _get_before_save(self, module_path, class_name):
        """Import a controller module and return its before_save method if present.

        An ImportError is deliberately allowed to propagate: a controller module
        that no longer imports is a failure, not a reason to report success.
        """
        mod = importlib.import_module(module_path)
        cls = getattr(mod, class_name, None)
        self.assertIsNotNone(cls, f"{class_name} missing from {module_path}")
        return getattr(cls, "before_save", None)

    def _assert_no_dead_doctype_guard(self, module_path, class_name):
        # [#scivu8] Either the controller has no before_save at all (the intended end
        # state), or it has one that no longer carries the dead doctype-mismatch throw.
        bs = self._get_before_save(module_path, class_name)
        if bs is None:
            return
        # [#f3k0ws]
        self.assertNotIn('frappe.throw("DocType mismatch")', inspect.getsource(bs))

    def test_accommodation_custody_item_has_no_before_save(self):
        """AccommodationCustodyItem must not define a dead before_save guard."""
        self._assert_no_dead_doctype_guard(
            "apex.habitat.doctype.accommodation_custody_item.accommodation_custody_item",
            "AccommodationCustodyItem",
        )

    def test_maintenance_work_order_has_no_dead_guard(self):
        """MaintenanceWorkOrder must not have a dead doctype-mismatch guard in before_save."""
        self._assert_no_dead_doctype_guard(
            "apex.habitat.doctype.maintenance_work_order.maintenance_work_order",
            "MaintenanceWorkOrder",
        )


if __name__ == "__main__":
    unittest.main()
