# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.apex_core.utils.company import company_for_vehicle


def _vehicle():
    return frappe.get_doc(
        {
            "doctype": "Salis Vehicle",
            "plate_number": "_T-FDL " + frappe.generate_hash(length=6),
            "status": "Active",
        }
    ).insert(ignore_permissions=True).name


def _log(vehicle, **overrides):
    fields = {
        "doctype": "Fuel Daily Log",
        "vehicle": vehicle,
        "log_date": frappe.utils.today(),
        "odometer": 1000,
        "litres": 40,
        "amount": 100,
    }
    fields.update(overrides)
    return frappe.get_doc(fields)


class TestFuelDailyLogOdometer(FrappeTestCase):
    def test_a_first_reading_is_accepted(self):
        doc = _log(_vehicle(), odometer=500).insert(ignore_permissions=True)
        self.assertEqual(doc.odometer, 500)

    def test_a_reading_lower_than_the_last_one_is_refused(self):
        vehicle = _vehicle()
        _log(vehicle, odometer=1000).insert(ignore_permissions=True)
        with self.assertRaisesRegex(frappe.ValidationError, "lower than the last reading"):
            _log(vehicle, odometer=900).insert(ignore_permissions=True)

    def test_a_reading_equal_to_the_last_one_is_accepted(self):
        vehicle = _vehicle()
        _log(vehicle, odometer=1000).insert(ignore_permissions=True)
        doc = _log(vehicle, odometer=1000).insert(ignore_permissions=True)
        self.assertEqual(doc.odometer, 1000)

    def test_a_reading_higher_than_the_last_one_is_accepted(self):
        vehicle = _vehicle()
        _log(vehicle, odometer=1000).insert(ignore_permissions=True)
        doc = _log(vehicle, odometer=1200).insert(ignore_permissions=True)
        self.assertEqual(doc.odometer, 1200)

    def test_another_vehicles_reading_does_not_bind_this_one(self):
        _log(_vehicle(), odometer=9000).insert(ignore_permissions=True)
        doc = _log(_vehicle(), odometer=100).insert(ignore_permissions=True)
        self.assertEqual(doc.odometer, 100)

    def test_a_log_with_no_reading_is_accepted(self):
        vehicle = _vehicle()
        _log(vehicle, odometer=1000).insert(ignore_permissions=True)
        doc = _log(vehicle, odometer=None).insert(ignore_permissions=True)
        self.assertFalse(doc.odometer)


class TestFuelDailyLogTimeline(FrappeTestCase):
    def test_inserting_a_log_writes_a_note_on_the_vehicle(self):
        vehicle = _vehicle()
        doc = _log(vehicle).insert(ignore_permissions=True)
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


class TestFuelDailyLogTrashReversesTheLedger(FrappeTestCase):
    def test_deleting_a_ledgered_log_posts_the_reversal(self):
        vehicle = _vehicle()
        doc = _log(vehicle).insert(ignore_permissions=True)
        original = frappe.get_doc(
            {
                "doctype": "Fuel Consumption Ledger",
                "vehicle": vehicle,
                "company": company_for_vehicle(vehicle),
                "period_month": str(doc.log_date)[:7],
                "litres": doc.litres,
                "amount": doc.amount,
                "source_type": "Fuel Daily Log",
                "source_doctype": "Fuel Daily Log",
                "source_name": doc.name,
                "logged_at": frappe.utils.now_datetime(),
            }
        ).insert(ignore_permissions=True)

        frappe.delete_doc("Fuel Daily Log", doc.name, ignore_permissions=True)

        reversal = frappe.db.get_value(
            "Fuel Consumption Ledger", {"reversal_of": original.name}, "litres"
        )
        self.assertEqual(reversal, -doc.litres)
