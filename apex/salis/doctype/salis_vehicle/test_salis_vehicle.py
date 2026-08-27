# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today

from apex.apex_core.doctype.salis_settings.salis_settings import get_salis_int
from apex.salis.doctype.salis_vehicle.salis_vehicle import DEFAULT_ALERT_LEAD_DAYS
from apex.tests.factories import make_test_driver


def _vehicle(**overrides):
    fields = {
        "doctype": "Salis Vehicle",
        "plate_number": "_T-VEH " + frappe.generate_hash(length=6),
        "status": "Active",
    }
    fields.update(overrides)
    return frappe.get_doc(fields)


def _lead_days():
    return get_salis_int("alert_lead_days", DEFAULT_ALERT_LEAD_DAYS)


def _compliance(expiry, compliance_type="Insurance"):
    return {"compliance_type": compliance_type, "expiry_date": expiry}


class TestSalisVehiclePlate(FrappeTestCase):
    def test_the_plate_is_stored_without_spaces_and_upper_cased(self):
        doc = _vehicle(plate_number=" abc 1234 ").insert(ignore_permissions=True)
        self.assertEqual(doc.plate_normalized, "ABC1234")

    def test_a_vehicle_with_no_company_is_filled_from_the_salis_default(self):
        doc = _vehicle().insert(ignore_permissions=True)
        self.assertTrue(doc.company)


class TestSalisVehicleDriverIsNotTyped(FrappeTestCase):
    def test_a_new_vehicle_naming_a_driver_is_refused(self):
        with self.assertRaises(frappe.PermissionError):
            _vehicle(current_driver=make_test_driver()).insert(ignore_permissions=True)

    def test_editing_the_driver_on_a_stored_vehicle_is_refused(self):
        doc = _vehicle().insert(ignore_permissions=True)
        doc.current_driver = make_test_driver()
        with self.assertRaises(frappe.PermissionError):
            doc.save(ignore_permissions=True)


class TestSalisVehicleStatusIsHeldByAnOpenStop(FrappeTestCase):
    def test_the_status_cannot_be_edited_while_a_stop_is_open(self):
        doc = _vehicle().insert(ignore_permissions=True)
        frappe.get_doc(
            {
                "doctype": "Vehicle Suspension",
                "vehicle": doc.name,
                "stop_reason": "Maintenance",
                "stop_date": today(),
            }
        ).insert(ignore_permissions=True).submit()

        doc.reload()
        doc.status = "Active"
        with self.assertRaisesRegex(frappe.PermissionError, "open stop"):
            doc.save(ignore_permissions=True)

    def test_a_vehicle_with_no_stop_may_change_status(self):
        doc = _vehicle().insert(ignore_permissions=True)
        doc.status = "Under Maintenance"
        doc.save(ignore_permissions=True)
        self.assertEqual(doc.status, "Under Maintenance")


class TestSalisVehicleCompliance(FrappeTestCase):
    def test_a_vehicle_with_no_document_is_not_tracked(self):
        doc = _vehicle().insert(ignore_permissions=True)
        self.assertEqual(doc.compliance_status, "Not Tracked")
        self.assertFalse(doc.next_expiry_date)

    def test_a_document_expiring_far_ahead_is_compliant(self):
        expiry = add_days(today(), _lead_days() + 30)
        doc = _vehicle(compliance_documents=[_compliance(expiry)]).insert(
            ignore_permissions=True
        )
        self.assertEqual(doc.compliance_status, "Compliant")
        self.assertEqual(doc.compliance_documents[0].status, "Valid")

    def test_a_document_inside_the_lead_window_is_expiring_soon(self):
        expiry = add_days(today(), max(_lead_days() - 1, 0))
        doc = _vehicle(compliance_documents=[_compliance(expiry)]).insert(
            ignore_permissions=True
        )
        self.assertEqual(doc.compliance_status, "Expiring Soon")

    def test_a_document_already_past_is_expired(self):
        doc = _vehicle(compliance_documents=[_compliance(add_days(today(), -1))]).insert(
            ignore_permissions=True
        )
        self.assertEqual(doc.compliance_status, "Expired")
        self.assertEqual(doc.compliance_documents[0].status, "Expired")

    def test_the_worst_document_decides_the_vehicle(self):
        doc = _vehicle(
            compliance_documents=[
                _compliance(add_days(today(), _lead_days() + 30), "Insurance"),
                _compliance(add_days(today(), -1), "Periodic Inspection"),
            ]
        ).insert(ignore_permissions=True)
        self.assertEqual(doc.compliance_status, "Expired")

    def test_the_next_expiry_is_the_nearest_one_still_ahead(self):
        near = add_days(today(), 5)
        doc = _vehicle(
            compliance_documents=[
                _compliance(add_days(today(), 400), "Insurance"),
                _compliance(near, "Periodic Inspection"),
            ]
        ).insert(ignore_permissions=True)
        self.assertEqual(str(doc.next_expiry_date), str(near))
