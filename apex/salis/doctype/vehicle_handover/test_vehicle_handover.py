# Copyright (c) 2026, afmcoltd
"""What a Vehicle Handover guarantees, asserted against the DocType itself.

A Transfer needs both a from- and a to-driver, and they must differ. The
odometer reading may not run backwards against the vehicle's current reading.
Submitting requires signed evidence, and moves the vehicle's current-driver
mirror to the incoming driver.

Scoped to ``direction="Transfer"``: Receipt and Return additionally require a
submitted, Active Vehicle Assignment and an exact native-checklist match
(``_validate_assignment_event`` / ``_validate_native_checklist``), which needs
a deeper fixture chain this pass does not build; a Transfer skips both checks
entirely, so it is the direction that isolates the guarantees below.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

test_dependencies = ["Salis Vehicle", "Salis Driver"]


class TestVehicleHandover(FrappeTestCase):
    def test_a_transfer_with_the_same_from_and_to_driver_is_refused(self):
        """A transfer to oneself is not a handover."""
        handover = frappe.copy_doc(frappe.get_test_records("Vehicle Handover")[0])
        handover.to_driver = handover.from_driver
        self.assertRaisesRegex(
            frappe.ValidationError,
            "To Driver must differ from From Driver",
            handover.insert,
        )

    def test_a_transfer_missing_either_driver_is_refused(self):
        """A transfer with no destination driver names no handover."""
        handover = frappe.copy_doc(frappe.get_test_records("Vehicle Handover")[0])
        handover.to_driver = None
        self.assertRaisesRegex(
            frappe.ValidationError,
            "From Driver and To Driver are required for a transfer",
            handover.insert,
        )

    def test_an_odometer_reading_lower_than_the_vehicles_current_is_refused(self):
        """A handover cannot record the vehicle's odometer running backwards.

        Raises VEH-000002's own odometer rather than VEH-000001's: nothing
        rolls back between test methods in this class, and VEH-000001 is what
        the other tests here insert their handovers against.
        """
        frappe.db.set_value("Salis Vehicle", "VEH-000002", "odometer", 5000)
        handover = frappe.copy_doc(frappe.get_test_records("Vehicle Handover")[1])
        handover.odometer_reading = 1000
        self.assertRaisesRegex(
            frappe.ValidationError,
            "cannot be lower than the vehicle's current",
            handover.insert,
        )

    def test_submitting_without_signed_evidence_is_refused(self):
        """A handover cannot be finalised without signed proof it happened."""
        handover = frappe.copy_doc(frappe.get_test_records("Vehicle Handover")[0])
        handover.signed_evidence = None
        handover.insert()
        self.assertRaisesRegex(
            frappe.ValidationError,
            "Signed handover evidence is required",
            handover.submit,
        )

    def test_submitting_moves_the_vehicles_current_driver_to_the_incoming_driver(self):
        """The whole point of a Transfer is that custody actually changes hands."""
        handover = frappe.copy_doc(frappe.get_test_records("Vehicle Handover")[0])
        handover.signed_evidence = "/files/_t-signed-handover.pdf"
        handover.insert()
        handover.submit()
        self.assertEqual(
            frappe.db.get_value("Salis Vehicle", "VEH-000001", "current_driver"),
            "DRV-000002",
        )
