# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today

from apex.tests.factories import default_company


def _vehicle(**overrides):
    fields = {
        "doctype": "Salis Vehicle",
        "plate_number": "_T-VA " + frappe.generate_hash(length=6),
        "status": "Active",
    }
    fields.update(overrides)
    return frappe.get_doc(fields).insert(ignore_permissions=True).name


def _driver():
    employee = frappe.get_doc(
        {
            "doctype": "Employee",
            "first_name": "_T-VA Driver " + frappe.generate_hash(length=6),
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
            "full_name": "_T-VA Driver",
        }
    ).insert(ignore_permissions=True).name


def _stopped_driver():
    driver = _driver()
    frappe.get_doc(
        {
            "doctype": "Driver Suspension",
            "driver": driver,
            "stop_reason": "Leave",
            "stop_date": today(),
        }
    ).insert(ignore_permissions=True).submit()
    return driver


def _assignment(vehicle=None, driver=None, **overrides):
    fields = {
        "doctype": "Vehicle Assignment",
        "vehicle": vehicle or _vehicle(),
        "driver": driver or _driver(),
        "start_date": today(),
        "status": "Active",
    }
    fields.update(overrides)
    return frappe.get_doc(fields)


class TestVehicleAssignmentDates(FrappeTestCase):
    def test_an_end_before_the_start_is_refused(self):
        with self.assertRaisesRegex(frappe.ValidationError, "End Date cannot be earlier"):
            _assignment(end_date=add_days(today(), -1)).insert(ignore_permissions=True)

    def test_an_end_after_the_start_is_accepted(self):
        doc = _assignment(end_date=add_days(today(), 10)).insert(ignore_permissions=True)
        self.assertEqual(doc.docstatus, 0)

    def test_an_open_ended_assignment_is_accepted(self):
        doc = _assignment().insert(ignore_permissions=True)
        self.assertFalse(doc.end_date)


class TestVehicleAssignmentRiderMustBeActive(FrappeTestCase):
    def test_a_stopped_rider_cannot_receive_a_vehicle(self):
        with self.assertRaisesRegex(frappe.ValidationError, "cannot receive a vehicle"):
            _assignment(driver=_stopped_driver()).insert(ignore_permissions=True)

    def test_an_active_rider_receives_the_vehicle(self):
        doc = _assignment().insert(ignore_permissions=True)
        self.assertEqual(doc.status, "Active")


class TestVehicleAssignmentNoOverlap(FrappeTestCase):
    def test_a_second_live_assignment_of_the_same_vehicle_is_refused(self):
        vehicle = _vehicle()
        _assignment(vehicle=vehicle).insert(ignore_permissions=True).submit()
        with self.assertRaisesRegex(frappe.ValidationError, "already has an active assignment"):
            _assignment(vehicle=vehicle).insert(ignore_permissions=True)

    def test_a_second_live_assignment_of_the_same_driver_is_refused(self):
        driver = _driver()
        _assignment(driver=driver).insert(ignore_permissions=True).submit()
        with self.assertRaisesRegex(frappe.ValidationError, "already has an active assignment"):
            _assignment(driver=driver).insert(ignore_permissions=True)

    def test_a_window_that_starts_after_the_first_one_ends_is_accepted(self):
        vehicle = _vehicle()
        _assignment(
            vehicle=vehicle, start_date=add_days(today(), -20), end_date=add_days(today(), -10)
        ).insert(ignore_permissions=True).submit()
        doc = _assignment(vehicle=vehicle, start_date=today()).insert(ignore_permissions=True)
        self.assertEqual(doc.vehicle, vehicle)

    def test_a_draft_assignment_does_not_block_another_one(self):
        vehicle = _vehicle()
        _assignment(vehicle=vehicle).insert(ignore_permissions=True)
        doc = _assignment(vehicle=vehicle).insert(ignore_permissions=True)
        self.assertEqual(doc.vehicle, vehicle)


class TestVehicleAssignmentPairsTheVehicleAndTheDriver(FrappeTestCase):
    def test_submitting_names_the_driver_on_the_vehicle(self):
        doc = _assignment().insert(ignore_permissions=True)
        doc.submit()
        self.assertEqual(
            frappe.db.get_value("Salis Vehicle", doc.vehicle, "current_driver"), doc.driver
        )

    def test_submitting_names_the_vehicle_on_the_driver(self):
        doc = _assignment().insert(ignore_permissions=True)
        doc.submit()
        self.assertEqual(
            frappe.db.get_value("Salis Driver", doc.driver, "current_vehicle"), doc.vehicle
        )

    def test_cancelling_releases_the_pairing_on_both_sides(self):
        doc = _assignment().insert(ignore_permissions=True)
        doc.submit()
        doc.cancel()
        self.assertFalse(frappe.db.get_value("Salis Vehicle", doc.vehicle, "current_driver"))
        self.assertFalse(frappe.db.get_value("Salis Driver", doc.driver, "current_vehicle"))
