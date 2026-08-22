# Copyright (c) 2026, afmcoltd
"""What a Salis Vehicle guarantees, asserted against the DocType itself.

``current_driver`` is Vehicle Assignment's mirror and a hand edit to it is
refused, at creation and later alike. ``status`` cannot be edited by hand
while an open Vehicle Suspension or Vehicle Incident owns the vehicle.
``compliance_status`` is always derived from the worst row in
``compliance_documents`` (Expired beats Expiring Soon beats Compliant), never
set directly, and a vehicle with no compliance rows reads Not Tracked.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today

test_dependencies = ["Salis Driver"]


class TestSalisVehicle(FrappeTestCase):
    def test_setting_current_driver_by_hand_at_creation_is_refused(self):
        """current_driver is Vehicle Assignment's mirror, refused even on a brand-new vehicle."""
        vehicle = frappe.copy_doc(frappe.get_test_records("Salis Vehicle")[0])
        vehicle.plate_number = "_T NEW 0001"
        vehicle.current_driver = "DRV-000001"
        self.assertRaisesRegex(
            frappe.PermissionError,
            "not by typing it here",
            vehicle.insert,
        )

    def test_editing_current_driver_by_hand_on_an_existing_vehicle_is_refused(self):
        """current_driver is set by assigning the vehicle, never by a plain save."""
        vehicle = frappe.copy_doc(frappe.get_test_records("Salis Vehicle")[0])
        vehicle.plate_number = "_T NEW 0002"
        vehicle.insert()
        vehicle.current_driver = "DRV-000001"
        self.assertRaisesRegex(
            frappe.PermissionError,
            "not by editing it",
            vehicle.save,
        )

    def test_editing_status_while_an_open_suspension_owns_the_vehicle_is_refused(self):
        """A stopped vehicle's status is not the operator's to change back by hand."""
        vehicle = frappe.copy_doc(frappe.get_test_records("Salis Vehicle")[0])
        vehicle.plate_number = "_T NEW 0003"
        vehicle.insert()

        frappe.get_doc(
            {
                "doctype": "Vehicle Suspension",
                "vehicle": vehicle.name,
                "stop_reason": "Maintenance",
                "stop_date": today(),
            }
        ).insert().submit()

        vehicle.reload()
        vehicle.status = "Active"
        self.assertRaisesRegex(
            frappe.PermissionError,
            "Close the stop",
            vehicle.save,
        )

    def test_a_vehicle_with_no_compliance_rows_reads_not_tracked(self):
        """No compliance data recorded must never silently read as Compliant."""
        vehicle = frappe.copy_doc(frappe.get_test_records("Salis Vehicle")[0])
        vehicle.plate_number = "_T NEW 0004"
        vehicle.compliance_documents = []
        vehicle.insert()
        self.assertEqual(vehicle.compliance_status, "Not Tracked")

    def test_compliance_status_reads_the_worst_row_expired_beats_expiring_soon(self):
        """One expired document must fail the whole vehicle even if another row is fine."""
        vehicle = frappe.copy_doc(frappe.get_test_records("Salis Vehicle")[0])
        vehicle.plate_number = "_T NEW 0005"
        vehicle.compliance_documents = []
        vehicle.append(
            "compliance_documents",
            {"compliance_type": "Registration (Istimara)", "expiry_date": add_days(today(), -1)},
        )
        vehicle.append(
            "compliance_documents",
            {"compliance_type": "Insurance", "expiry_date": add_days(today(), 3650)},
        )
        vehicle.insert()
        self.assertEqual(vehicle.compliance_status, "Expired")
