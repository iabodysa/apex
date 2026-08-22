# Copyright (c) 2026, afmcoltd
"""What a Vehicle Incident guarantees, asserted against the DocType itself.

The incident date cannot be in the future, and the estimated cost cannot be
negative. ``status`` is controller-owned: a new incident always opens
Active, and a hand edit to ``status`` on an existing incident is refused. A
submitted Theft incident takes the vehicle out of service (status Stopped)
and clears its current driver; cancelling restores the vehicle's prior
status. A cost recovery needs a positive amount to recover.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today

test_dependencies = ["Salis Vehicle", "Employee"]


class TestVehicleIncident(FrappeTestCase):
    def test_a_future_incident_date_is_refused(self):
        """An incident cannot be reported as having happened tomorrow."""
        incident = frappe.copy_doc(frappe.get_test_records("Vehicle Incident")[0])
        incident.incident_date = add_days(today(), 1)
        self.assertRaisesRegex(
            frappe.ValidationError,
            "Incident date cannot be in the future",
            incident.insert,
        )

    def test_a_negative_estimated_cost_is_refused(self):
        """An incident cannot claim a negative cost."""
        incident = frappe.copy_doc(frappe.get_test_records("Vehicle Incident")[0])
        incident.estimated_cost = -1
        self.assertRaisesRegex(
            frappe.ValidationError,
            "Estimated cost cannot be negative",
            incident.insert,
        )

    def test_editing_status_by_hand_on_an_existing_incident_is_refused(self):
        """Status moves only through the incident's own controller-owned transitions."""
        incident = frappe.copy_doc(frappe.get_test_records("Vehicle Incident")[0])
        incident.insert()
        incident.status = "Closed"
        self.assertRaisesRegex(
            frappe.PermissionError,
            "Use the incident actions to change Status",
            incident.save,
        )

    def test_a_recovery_with_a_zero_or_negative_amount_is_refused(self):
        """A wage recovery must recover something, or it is not a recovery."""
        incident = frappe.copy_doc(frappe.get_test_records("Vehicle Incident")[0])
        incident.recover_from_driver = 1
        incident.recovery_employee = "_T-Employee-00001"
        incident.recovery_amount = 0
        self.assertRaisesRegex(
            frappe.ValidationError,
            "Amount to Recover must be greater than zero",
            incident.insert,
        )

    def test_submitting_a_theft_stops_the_vehicle_and_cancel_restores_it(self):
        """Taking a stolen vehicle out of service, and undoing that on cancel, is the point of a Theft incident."""
        incident = frappe.copy_doc(frappe.get_test_records("Vehicle Incident")[1])
        incident.insert()
        incident.submit()
        self.assertEqual(frappe.db.get_value("Salis Vehicle", "VEH-000002", "status"), "Stopped")

        incident.cancel()
        self.assertEqual(frappe.db.get_value("Salis Vehicle", "VEH-000002", "status"), "Active")
