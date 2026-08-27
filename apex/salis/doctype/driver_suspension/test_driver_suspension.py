# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today

from apex.tests.factories import default_company


def _vehicle():
    return frappe.get_doc(
        {
            "doctype": "Salis Vehicle",
            "plate_number": "_T-DS " + frappe.generate_hash(length=6),
            "status": "Active",
        }
    ).insert(ignore_permissions=True).name


def _driver():
    employee = frappe.get_doc(
        {
            "doctype": "Employee",
            "first_name": "_T-DS Driver " + frappe.generate_hash(length=6),
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
            "full_name": "_T-DS Driver",
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


def _stop(driver=None, **overrides):
    fields = {
        "doctype": "Driver Suspension",
        "driver": driver or _driver(),
        "stop_reason": "Leave",
        "stop_date": today(),
    }
    fields.update(overrides)
    return frappe.get_doc(fields)


class TestDriverSuspensionVehicleToRelease(FrappeTestCase):
    def test_releasing_a_vehicle_without_naming_it_is_refused(self):
        with self.assertRaisesRegex(frappe.ValidationError, "Select the vehicle to release"):
            _stop(release_vehicle=1).insert(ignore_permissions=True)

    def test_a_stop_that_releases_no_vehicle_needs_none(self):
        doc = _stop().insert(ignore_permissions=True)
        self.assertFalse(doc.related_vehicle)


class TestDriverSuspensionEvidence(FrappeTestCase):
    def test_a_violation_stop_without_evidence_cannot_be_submitted(self):
        doc = _stop(stop_reason="Violation").insert(ignore_permissions=True)
        with self.assertRaisesRegex(frappe.ValidationError, "Evidence is required"):
            doc.submit()

    def test_a_termination_stop_without_evidence_cannot_be_submitted(self):
        doc = _stop(stop_reason="Termination").insert(ignore_permissions=True)
        with self.assertRaisesRegex(frappe.ValidationError, "Evidence is required"):
            doc.submit()

    def test_a_leave_stop_needs_no_evidence(self):
        doc = _stop().insert(ignore_permissions=True)
        doc.submit()
        self.assertEqual(doc.docstatus, 1)


class TestDriverSuspensionStopsTheDriver(FrappeTestCase):
    def test_submitting_a_stop_marks_the_driver_stopped(self):
        driver = _driver()
        _stop(driver).insert(ignore_permissions=True).submit()
        self.assertEqual(frappe.db.get_value("Salis Driver", driver, "status"), "Stopped")

    def test_the_status_the_driver_held_is_remembered_on_the_stop(self):
        driver = _driver()
        doc = _stop(driver).insert(ignore_permissions=True)
        doc.submit()
        self.assertEqual(doc.previous_status, "Active")

    def test_cancelling_the_only_stop_restores_the_status(self):
        driver = _driver()
        doc = _stop(driver).insert(ignore_permissions=True)
        doc.submit()
        doc.cancel()
        self.assertEqual(frappe.db.get_value("Salis Driver", driver, "status"), "Active")

    def test_a_second_stop_keeps_the_driver_stopped_when_the_first_is_cancelled(self):
        driver = _driver()
        first = _stop(driver).insert(ignore_permissions=True)
        first.submit()
        second = _stop(driver).insert(ignore_permissions=True)
        second.submit()
        first.cancel()
        self.assertEqual(frappe.db.get_value("Salis Driver", driver, "status"), "Stopped")


class TestDriverSuspensionReleasesTheVehicle(FrappeTestCase):
    def test_a_released_vehicle_loses_its_driver_and_is_marked_released(self):
        driver, vehicle = _paired()
        _stop(driver, release_vehicle=1, related_vehicle=vehicle).insert(
            ignore_permissions=True
        ).submit()
        self.assertFalse(frappe.db.get_value("Salis Vehicle", vehicle, "current_driver"))
        self.assertEqual(frappe.db.get_value("Salis Vehicle", vehicle, "status"), "Released")
        self.assertFalse(frappe.db.get_value("Salis Driver", driver, "current_vehicle"))

    def test_a_stop_that_releases_nothing_leaves_the_pairing_alone(self):
        driver, vehicle = _paired()
        _stop(driver).insert(ignore_permissions=True).submit()
        self.assertEqual(
            frappe.db.get_value("Salis Vehicle", vehicle, "current_driver"), driver
        )

    def test_cancelling_a_release_re_links_a_vehicle_that_is_still_free(self):
        driver, vehicle = _paired()
        doc = _stop(driver, release_vehicle=1, related_vehicle=vehicle).insert(
            ignore_permissions=True
        )
        doc.submit()
        doc.cancel()
        self.assertEqual(
            frappe.db.get_value("Salis Vehicle", vehicle, "current_driver"), driver
        )
        self.assertEqual(frappe.db.get_value("Salis Vehicle", vehicle, "status"), "Active")
