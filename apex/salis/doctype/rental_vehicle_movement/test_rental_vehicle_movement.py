# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today

from apex.apex_core.utils.company import company_for_vehicle
from apex.tests.factories import make_rental_office


def _office():
    return make_rental_office("_T-RVM Office")


def _vehicle(ownership="Rented"):
    return frappe.get_doc(
        {
            "doctype": "Salis Vehicle",
            "plate_number": "_T-RVM " + frappe.generate_hash(length=6),
            "status": "Active",
            "ownership": ownership,
            "rental_office": _office() if ownership == "Rented" else None,
        }
    ).insert(ignore_permissions=True).name


def _movement(vehicle, **overrides):
    fields = {
        "doctype": "Rental Vehicle Movement",
        "movement_type": "Receipt",
        "vehicle": vehicle,
        "rental_office": _office(),
        "movement_date": today(),
        "daily_rate": 150,
    }
    fields.update(overrides)
    return frappe.get_doc(fields)


def _received(vehicle, **overrides):
    doc = _movement(vehicle, **overrides).insert(ignore_permissions=True)
    doc.submit()
    return doc


class TestRentalVehicleMovementOwnership(FrappeTestCase):
    def test_an_owned_vehicle_cannot_be_received_on_rent(self):
        with self.assertRaisesRegex(frappe.ValidationError, "not a rented vehicle"):
            _movement(_vehicle(ownership="Owned")).insert(ignore_permissions=True)

    def test_a_rented_vehicle_is_accepted(self):
        doc = _movement(_vehicle()).insert(ignore_permissions=True)
        self.assertEqual(doc.movement_type, "Receipt")


class TestRentalVehicleMovementDailyRate(FrappeTestCase):
    def test_a_receipt_without_a_daily_rate_is_refused(self):
        with self.assertRaisesRegex(frappe.ValidationError, "Daily Rate is required"):
            _movement(_vehicle(), daily_rate=None).insert(ignore_permissions=True)

    def test_a_negative_daily_rate_is_refused(self):
        with self.assertRaisesRegex(frappe.ValidationError, "cannot be negative"):
            _movement(_vehicle(), daily_rate=-1).insert(ignore_permissions=True)

    def test_a_return_needs_no_daily_rate(self):
        vehicle = _vehicle()
        _received(vehicle)
        doc = _movement(vehicle, movement_type="Return", daily_rate=None).insert(
            ignore_permissions=True
        )
        self.assertEqual(doc.movement_type, "Return")


class TestRentalVehicleMovementLifecycle(FrappeTestCase):
    def test_a_return_with_no_open_receipt_is_refused(self):
        with self.assertRaisesRegex(frappe.ValidationError, "no open rental Receipt"):
            _movement(_vehicle(), movement_type="Return").insert(ignore_permissions=True)

    def test_a_second_receipt_while_one_is_open_is_refused(self):
        vehicle = _vehicle()
        _received(vehicle)
        with self.assertRaisesRegex(frappe.ValidationError, "already has an open rental Receipt"):
            _movement(vehicle).insert(ignore_permissions=True)

    def test_a_return_dated_before_the_open_receipt_is_refused(self):
        vehicle = _vehicle()
        _received(vehicle, movement_date=today())
        with self.assertRaisesRegex(frappe.ValidationError, "cannot be earlier than the open Receipt"):
            _movement(
                vehicle, movement_type="Return", movement_date=add_days(today(), -1)
            ).insert(ignore_permissions=True)

    def test_a_receipt_after_the_vehicle_was_returned_is_accepted(self):
        vehicle = _vehicle()
        _received(vehicle, movement_date=add_days(today(), -10))
        _received(vehicle, movement_type="Return", movement_date=add_days(today(), -5))
        doc = _movement(vehicle, movement_date=today()).insert(ignore_permissions=True)
        self.assertEqual(doc.movement_type, "Receipt")


class TestRentalVehicleMovementTimeline(FrappeTestCase):
    def test_submitting_writes_a_note_on_the_vehicle(self):
        vehicle = _vehicle()
        doc = _received(vehicle)
        self.assertTrue(
            frappe.db.exists(
                "Comment",
                {
                    "reference_doctype": "Salis Vehicle",
                    "reference_name": vehicle,
                    "content": ["like", "%" + doc.name + "%"],
                },
            )
        )


class TestRentalVehicleMovementCancelReversesTheAccrual(FrappeTestCase):
    def test_cancelling_a_receipt_posts_the_reversal(self):
        vehicle = _vehicle()
        doc = _received(vehicle)
        original = frappe.get_doc(
            {
                "doctype": "Rental Accrual Ledger",
                "vehicle": vehicle,
                "rental_office": doc.rental_office,
                "company": company_for_vehicle(vehicle),
                "accrual_date": doc.movement_date,
                "amount": doc.daily_rate,
                "source_doctype": "Rental Vehicle Movement",
                "source_name": doc.name,
            }
        ).insert(ignore_permissions=True)

        doc.cancel()

        self.assertEqual(
            frappe.db.get_value("Rental Accrual Ledger", {"reversal_of": original.name}, "amount"),
            -doc.daily_rate,
        )
