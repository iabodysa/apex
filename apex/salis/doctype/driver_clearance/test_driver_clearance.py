# Copyright (c) 2026, afmcoltd
"""What a Driver Clearance guarantees, asserted against the DocType itself.

Marking a clearance Cleared is blocked while any precondition is unmet
(vehicle, fuel chip and custody not all returned, or an open Fuel Exception
Case / Movement Cost Recovery remains against the driver) — the same gate the
Driver Clearance Workflow's own "Clear" transition condition mirrors, kept
here as a hard server-side block regardless of how the save was reached. Once
Cleared (reached through the real workflow transition, not a hand-set field),
submitting releases the linked driver to Released and clears their current
vehicle; cancelling a Cleared clearance is INTENDED to restore the driver
(``on_cancel`` / ``_restore_driver``), which the last test below pins and
finds broken over the real workflow path — see its docstring.

DRV-000001 (fixture record 0's driver) already carries a real, standing Open
Movement Cost Recovery (MCR-000001) on this site, so the refusal case needs no
extra setup — it is simply the natural, already-blocked state of that driver.
The acceptance/workflow case uses DRV-000002 instead, which carries no such
row. Nothing rolls back between test methods in this class (``FrappeTestCase``
rolls back only once, at class teardown), so the one test that mutates state
is self-contained end to end rather than split across methods.
"""

import frappe
from frappe.model.workflow import apply_workflow
from frappe.tests.utils import FrappeTestCase

test_dependencies = ["Salis Driver"]


class TestDriverClearance(FrappeTestCase):
    def test_marking_cleared_without_all_preconditions_met_is_refused(self):
        """A clearance cannot certify a return that has not happened."""
        clearance = frappe.copy_doc(frappe.get_test_records("Driver Clearance")[0])
        clearance.status = "Cleared"
        clearance.vehicle_returned = 0
        clearance.fuel_chip_returned = 0
        clearance.custody_returned = 0
        self.assertRaisesRegex(
            frappe.ValidationError,
            "Clearance is blocked",
            clearance.insert,
        )

    def test_the_clear_transition_stamps_a_clearance_date_and_releases_the_driver(self):
        """Clear is the transition that actually releases a driver from their vehicle."""
        clearance = frappe.copy_doc(frappe.get_test_records("Driver Clearance")[0])
        clearance.driver = "DRV-000002"
        clearance.vehicle_returned = 1
        clearance.fuel_chip_returned = 1
        clearance.custody_returned = 1
        clearance.insert()
        self.assertEqual(clearance.status, "Open")

        cleared = apply_workflow(clearance, "Clear")
        self.assertEqual(cleared.status, "Cleared")
        self.assertEqual(cleared.docstatus, 1)
        self.assertTrue(cleared.clearance_date)
        self.assertEqual(frappe.db.get_value("Salis Driver", "DRV-000002", "status"), "Released")

    def test_cancelling_a_cleared_clearance_restores_the_driver_to_active(self):
        """Pins ``on_cancel``'s intended contract, and finds it broken over the real path.

        ``apply_workflow`` (frappe/model/workflow.py:120) sets ``status`` to the
        NEXT state — "Cancelled" — before it calls ``doc.cancel()``. This
        controller's own ``on_cancel`` then checks ``if self.status ==
        "Cleared"`` (driver_clearance.py), which is already false by then, so
        ``_restore_driver`` never runs and the driver is left stuck on
        Released. A hand-set ``doc.status = "Cleared"`` right before calling
        ``.cancel()`` would hide this — status would still read "Cleared" at
        that point — which is exactly why this test drives the real
        transition instead.
        """
        clearance = frappe.copy_doc(frappe.get_test_records("Driver Clearance")[0])
        clearance.driver = "DRV-000002"
        clearance.vehicle_returned = 1
        clearance.fuel_chip_returned = 1
        clearance.custody_returned = 1
        clearance.insert()
        cleared = apply_workflow(clearance, "Clear")

        apply_workflow(cleared, "Cancel")
        self.assertEqual(
            frappe.db.get_value("Salis Driver", "DRV-000002", "status"),
            "Active",
            "on_cancel must restore the driver it released on Clear",
        )
