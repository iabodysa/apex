# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.tests.factories import make_employee


def _endpoint():
    return "https://fcm.googleapis.com/fcm/send/" + frappe.generate_hash(length=12)


def _subscription(**overrides):
    fields = {
        "doctype": "Portal Push Subscription",
        "holder_type": "Worker",
        "endpoint": _endpoint(),
        "p256dh": frappe.generate_hash(length=20),
        "auth": frappe.generate_hash(length=12),
    }
    fields.update(overrides)
    return frappe.get_doc(fields)


def _driver():
    return frappe.get_doc(
        {
            "doctype": "Salis Driver",
            "full_name": "_T-Push Driver " + frappe.generate_hash(length=6),
            "status": "Active",
        }
    ).insert(ignore_permissions=True).name


class TestPortalPushSubscriptionHolder(FrappeTestCase):
    def test_a_worker_device_with_no_employee_is_refused(self):
        with self.assertRaises(frappe.ValidationError):
            _subscription().insert(ignore_permissions=True)

    def test_a_worker_device_naming_a_driver_too_is_refused(self):
        doc = _subscription(employee=make_employee("_T-Push Worker").name, driver=_driver())
        with self.assertRaises(frappe.ValidationError):
            doc.insert(ignore_permissions=True)

    def test_a_driver_device_with_no_driver_is_refused(self):
        with self.assertRaises(frappe.ValidationError):
            _subscription(holder_type="Driver").insert(ignore_permissions=True)

    def test_a_driver_device_naming_an_employee_too_is_refused(self):
        doc = _subscription(
            holder_type="Driver",
            driver=_driver(),
            employee=make_employee("_T-Push Worker").name,
        )
        with self.assertRaises(frappe.ValidationError):
            doc.insert(ignore_permissions=True)

    def test_a_worker_device_naming_one_employee_is_accepted(self):
        doc = _subscription(employee=make_employee("_T-Push Worker").name).insert(
            ignore_permissions=True
        )
        self.assertEqual(doc.holder_type, "Worker")


class TestPortalPushSubscriptionEndpoint(FrappeTestCase):
    def test_an_endpoint_outside_the_approved_push_services_is_refused(self):
        doc = _subscription(
            employee=make_employee("_T-Push Worker").name,
            endpoint="https://push.example.com/send/" + frappe.generate_hash(length=8),
        )
        with self.assertRaises(frappe.ValidationError):
            doc.insert(ignore_permissions=True)

    def test_a_plain_http_endpoint_is_refused(self):
        doc = _subscription(
            employee=make_employee("_T-Push Worker").name,
            endpoint="http://fcm.googleapis.com/fcm/send/" + frappe.generate_hash(length=8),
        )
        with self.assertRaises(frappe.ValidationError):
            doc.insert(ignore_permissions=True)


class TestPortalPushSubscriptionOneRowPerEndpoint(FrappeTestCase):
    def test_a_second_row_for_one_endpoint_is_refused(self):
        employee = make_employee("_T-Push Worker").name
        endpoint = _endpoint()
        _subscription(employee=employee, endpoint=endpoint).insert(ignore_permissions=True)
        with self.assertRaises(frappe.DuplicateEntryError):
            _subscription(employee=employee, endpoint=endpoint).insert(ignore_permissions=True)
