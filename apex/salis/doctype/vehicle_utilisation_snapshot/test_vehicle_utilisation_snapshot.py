# Copyright (c) 2026, afmcoltd
"""What a Vehicle Utilisation Snapshot guarantees, asserted against the DocType itself.

This is a submitted point-in-time snapshot, not a report view: its numbers
(``trips_count``, ``idle_days``, ``utilisation_pct``) cannot be recomputed
once live data moves, so they are frozen at the row's own creation rather
than derived on read. Its one real guarantee is the DB-level backstop
``on_doctype_update`` adds: a composite UNIQUE index on ``(vehicle,
snapshot_date)`` (``unique_vus_vehicle_date``), so the weekly scheduler cannot
double-post one vehicle's week even if its own check-then-insert is bypassed
by a race. Unlike the ``reversal_of``-keyed ledgers elsewhere in this module,
this key has no nullable column, so it is not exposed to their NULL-never-
equals-NULL gap.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

test_dependencies = ["Salis Vehicle"]


class TestVehicleUtilisationSnapshot(FrappeTestCase):
    def test_a_second_snapshot_for_the_same_vehicle_and_date_is_refused(self):
        """One vehicle-week must never post two utilisation snapshots."""
        duplicate = frappe.copy_doc(frappe.get_test_records("Vehicle Utilisation Snapshot")[0])
        self.assertRaisesRegex(
            frappe.UniqueValidationError,
            "unique_vus_vehicle_date",
            duplicate.insert,
        )
