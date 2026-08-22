# Copyright (c) 2026, afmcoltd
"""What a Vehicle Suspension guarantees, asserted against the DocType itself.

Submitting an Accident or Violation stop requires evidence; a Maintenance
stop does not. Submitting stops the vehicle and records its prior status;
cancelling restores it, unless another stop is still in force.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

test_dependencies = ["Salis Vehicle"]


class TestVehicleSuspension(FrappeTestCase):
    def test_submitting_an_accident_stop_without_evidence_is_refused(self):
        """An accident stop needs proof before it can take effect."""
        stop = frappe.copy_doc(frappe.get_test_records("Vehicle Suspension")[1])
        stop.evidence = None
        stop.insert()
        self.assertRaisesRegex(
            frappe.ValidationError,
            "Evidence is required",
            stop.submit,
        )

    def test_submitting_a_maintenance_stop_stops_the_vehicle_and_cancel_restores_it(self):
        """Stopping the vehicle and restoring it on cancel is the whole point of a stop."""
        stop = frappe.copy_doc(frappe.get_test_records("Vehicle Suspension")[0])
        stop.insert()
        stop.submit()
        self.assertEqual(frappe.db.get_value("Salis Vehicle", "VEH-000001", "status"), "Stopped")

        stop.cancel()
        self.assertEqual(frappe.db.get_value("Salis Vehicle", "VEH-000001", "status"), "Active")
