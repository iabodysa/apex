# Copyright (c) 2026, afmcoltd
"""What an Occupancy Snapshot guarantees, asserted against the DocType itself.

Patterned on frappe's own document-persistence tests (``frappe/tests/test_document.py``,
e.g. ``test_conflict_validation``): the subject here is a DB-level guarantee, not app
validation logic, so the test drives it through the real door — ``insert()`` — and reads
the outcome back from the database rather than from the exception alone.

Occupancy Snapshot is a scheduler-written time series (one row per building per day). Its
only guarantee beyond its schema is ``on_doctype_update``'s composite UNIQUE index on
``(building, snapshot_date)`` (``apex.apex_core.utils.ledger_index.add_unique_guarded``),
the hard backstop for the app-level check-then-insert guard in
``habitat.tasks.daily_occupancy_snapshot``. A race that defeats the app-level guard must
still be stopped by the database, or the same building/day gets counted twice.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

test_dependencies = ["Building"]


class TestOccupancySnapshot(FrappeTestCase):
    def test_posting_the_same_building_and_date_twice_is_refused(self):
        """``Occupancy Snapshot`` is included in its own ``test_dependencies`` resolution
        (a DocType is always a dependency of its own ``test_records.json``), so the fixture
        row already stands before this test runs — copying it verbatim IS the duplicate
        attempt. Without the unique index this second insert would silently double the
        building's count for that day."""
        duplicate = frappe.copy_doc(frappe.get_test_records("Occupancy Snapshot")[0])
        self.assertRaises(frappe.UniqueValidationError, duplicate.insert)

        # A duplicate that was refused and a post that never happened look identical if only
        # the exception is checked — so the row count is asserted too.
        self.assertEqual(
            frappe.db.count(
                "Occupancy Snapshot",
                {"building": duplicate.building, "snapshot_date": duplicate.snapshot_date},
            ),
            1,
        )

    def test_posting_a_new_building_and_date_combination_is_accepted(self):
        """The index is scoped to (building, snapshot_date) together — a genuinely new day
        for a building that already has standing snapshots must still post."""
        fresh = frappe.copy_doc(frappe.get_test_records("Occupancy Snapshot")[0])
        fresh.snapshot_date = "2026-06-01"
        fresh.insert()

        self.assertEqual(
            frappe.db.count(
                "Occupancy Snapshot",
                {"building": fresh.building, "snapshot_date": "2026-06-01"},
            ),
            1,
        )
