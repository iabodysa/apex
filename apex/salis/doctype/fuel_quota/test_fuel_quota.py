# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase


def _vehicle():
    return frappe.get_doc(
        {
            "doctype": "Salis Vehicle",
            "plate_number": "_T-FQ " + frappe.generate_hash(length=6),
            "status": "Active",
        }
    ).insert(ignore_permissions=True).name


def _quota(vehicle, **overrides):
    fields = {
        "doctype": "Fuel Quota",
        "vehicle": vehicle,
        "period_month": "2026-01",
        "monthly_litres": 400,
        "status": "Active",
    }
    fields.update(overrides)
    return frappe.get_doc(fields)


class TestFuelQuotaMonthlyLitres(FrappeTestCase):
    def test_a_zero_monthly_quota_is_refused(self):
        with self.assertRaisesRegex(frappe.ValidationError, "greater than zero"):
            _quota(_vehicle(), monthly_litres=0).insert(ignore_permissions=True)

    def test_a_negative_monthly_quota_is_refused(self):
        with self.assertRaisesRegex(frappe.ValidationError, "greater than zero"):
            _quota(_vehicle(), monthly_litres=-1).insert(ignore_permissions=True)

    def test_a_positive_monthly_quota_is_accepted(self):
        doc = _quota(_vehicle()).insert(ignore_permissions=True)
        self.assertEqual(doc.monthly_litres, 400)


class TestFuelQuotaOnePerVehiclePerPeriod(FrappeTestCase):
    def test_a_second_quota_for_the_same_vehicle_and_period_is_refused(self):
        vehicle = _vehicle()
        _quota(vehicle).insert(ignore_permissions=True)
        with self.assertRaisesRegex(frappe.ValidationError, "already exists for vehicle"):
            _quota(vehicle).insert(ignore_permissions=True)

    def test_the_same_vehicle_in_another_period_is_accepted(self):
        vehicle = _vehicle()
        _quota(vehicle, period_month="2026-01").insert(ignore_permissions=True)
        doc = _quota(vehicle, period_month="2026-02").insert(ignore_permissions=True)
        self.assertEqual(doc.period_month, "2026-02")

    def test_another_vehicle_in_the_same_period_is_accepted(self):
        _quota(_vehicle()).insert(ignore_permissions=True)
        doc = _quota(_vehicle()).insert(ignore_permissions=True)
        self.assertEqual(doc.period_month, "2026-01")

    def test_saving_the_same_quota_again_does_not_collide_with_itself(self):
        doc = _quota(_vehicle()).insert(ignore_permissions=True)
        doc.monthly_amount = 900
        doc.save(ignore_permissions=True)
        self.assertEqual(doc.monthly_amount, 900)

    def test_a_cancelled_quota_leaves_the_period_free(self):
        vehicle = _vehicle()
        first = _quota(vehicle).insert(ignore_permissions=True)
        first.submit()
        first.cancel()
        doc = _quota(vehicle).insert(ignore_permissions=True)
        self.assertEqual(doc.vehicle, vehicle)
