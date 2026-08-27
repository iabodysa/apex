# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.model.workflow import WorkflowTransitionError, apply_workflow
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today

from apex.tests.factories import default_company


def _vehicle():
    return frappe.get_doc(
        {
            "doctype": "Salis Vehicle",
            "plate_number": "_T-DCL " + frappe.generate_hash(length=6),
            "status": "Active",
        }
    ).insert(ignore_permissions=True).name


def _driver():
    employee = frappe.get_doc(
        {
            "doctype": "Employee",
            "first_name": "_T-DCL Driver " + frappe.generate_hash(length=6),
            "date_of_birth": "1990-01-01",
            "date_of_joining": "2020-01-01",
            "gender": "Male",
            "company": default_company(),
        }
    ).insert(ignore_permissions=True).name
    return frappe.get_doc(
        {
            "doctype": "Salis Driver",
            "employee": employee,
            "full_name": "_T-DCL Driver",
        }
    ).insert(ignore_permissions=True).name


def _paired():
    driver, vehicle = _driver(), _vehicle()
    frappe.get_doc(
        {
            "doctype": "Vehicle Assignment",
            "vehicle": vehicle,
            "driver": driver,
            "start_date": today(),
            "status": "Active",
        }
    ).insert(ignore_permissions=True).submit()
    return driver, vehicle


def _planned_trip(driver):
    return frappe.get_doc(
        {
            "doctype": "Dispatch Trip",
            "trip_type": "Ad Hoc",
            "trip_date": today(),
            "driver": driver,
            "status": "Planned",
        }
    ).insert(ignore_permissions=True).name


def _open_recovery(driver):
    return frappe.get_doc(
        {
            "doctype": "Movement Cost Recovery",
            "recovery_type": "Vehicle Damage",
            "driver": driver,
            "amount": 100,
            "basis_evidence": "/files/_t_dcl_evidence.pdf",
            "request_date": today(),
            "status": "Open",
        }
    ).insert(ignore_permissions=True).name


def _clearance(driver=None, **overrides):
    fields = {
        "doctype": "Driver Clearance",
        "driver": driver or _driver(),
        "clearance_reason": "Resignation",
        "status": "Open",
        "vehicle_returned": 1,
        "fuel_chip_returned": 1,
        "custody_returned": 1,
    }
    fields.update(overrides)
    return frappe.get_doc(fields)


class TestDriverClearanceOutstanding(FrappeTestCase):
    def test_a_driver_owing_nothing_counts_zero(self):
        doc = _clearance().insert(ignore_permissions=True)
        self.assertEqual(doc.outstanding_recoveries, 0)
        self.assertEqual(doc.outstanding_fuel_exceptions, 0)
        self.assertEqual(doc.outstanding_recovery_amount, 0)

    def test_an_open_recovery_is_counted_with_its_amount(self):
        driver = _driver()
        _open_recovery(driver)
        doc = _clearance(driver).insert(ignore_permissions=True)
        self.assertEqual(doc.outstanding_recoveries, 1)
        self.assertEqual(doc.outstanding_recovery_amount, 100)


class TestDriverClearanceBlockedUntilEverythingIsBack(FrappeTestCase):
    def test_clearing_without_the_vehicle_back_is_refused(self):
        doc = _clearance(vehicle_returned=0).insert(ignore_permissions=True)
        doc.status = "Cleared"
        with self.assertRaisesRegex(frappe.ValidationError, "Vehicle Returned"):
            doc.save(ignore_permissions=True)

    def test_clearing_without_the_fuel_chip_back_is_refused(self):
        doc = _clearance(fuel_chip_returned=0).insert(ignore_permissions=True)
        doc.status = "Cleared"
        with self.assertRaisesRegex(frappe.ValidationError, "Fuel Chip Returned"):
            doc.save(ignore_permissions=True)

    def test_clearing_without_the_custody_back_is_refused(self):
        doc = _clearance(custody_returned=0).insert(ignore_permissions=True)
        doc.status = "Cleared"
        with self.assertRaisesRegex(frappe.ValidationError, "Custody Returned"):
            doc.save(ignore_permissions=True)

    def test_clearing_with_an_open_recovery_is_refused(self):
        driver = _driver()
        _open_recovery(driver)
        doc = _clearance(driver).insert(ignore_permissions=True)
        doc.status = "Cleared"
        with self.assertRaisesRegex(frappe.ValidationError, "Open Movement Cost Recoveries"):
            doc.save(ignore_permissions=True)

    def test_clearing_while_trips_are_still_his_is_refused(self):
        driver = _driver()
        _planned_trip(driver)
        doc = _clearance(driver).insert(ignore_permissions=True)
        with self.assertRaisesRegex(frappe.ValidationError, "Planned trips still assigned"):
            apply_workflow(doc, "Clear")

    def test_the_workflow_offers_no_clear_while_something_is_outstanding(self):
        doc = _clearance(vehicle_returned=0).insert(ignore_permissions=True)
        with self.assertRaises(WorkflowTransitionError):
            apply_workflow(doc, "Clear")


class TestDriverClearanceDate(FrappeTestCase):
    def test_an_open_clearance_carries_no_date(self):
        doc = _clearance().insert(ignore_permissions=True)
        self.assertFalse(doc.clearance_date)

    def test_clearing_stamps_the_date(self):
        doc = _clearance().insert(ignore_permissions=True)
        apply_workflow(doc, "Clear")
        self.assertEqual(str(doc.clearance_date), today())


class TestDriverClearanceReleasesTheDriver(FrappeTestCase):
    def test_submitting_a_cleared_clearance_releases_the_driver_and_the_vehicle(self):
        driver, vehicle = _paired()
        doc = _clearance(driver).insert(ignore_permissions=True)
        apply_workflow(doc, "Clear")
        doc.submit()
        self.assertEqual(frappe.db.get_value("Salis Driver", driver, "status"), "Released")
        self.assertFalse(frappe.db.get_value("Salis Driver", driver, "current_vehicle"))
        self.assertFalse(frappe.db.get_value("Salis Vehicle", vehicle, "current_driver"))

    def test_cancelling_a_cleared_clearance_restores_the_driver(self):
        driver, _vehicle_name = _paired()
        doc = _clearance(driver).insert(ignore_permissions=True)
        apply_workflow(doc, "Clear")
        doc.submit()
        doc.cancel()
        self.assertEqual(frappe.db.get_value("Salis Driver", driver, "status"), "Active")
