# Copyright (c) 2026, afmcoltd


import frappe
from frappe.tests.utils import FrappeTestCase

from apex.habitat.doctype.utility_bill_entry.utility_bill_entry import (
    _compute_meter_readings,
    _compute_sharing,
)

test_ignore = ["Payment Entry"]


class TestMeterReadings(FrappeTestCase):

    def test_consumption_is_the_difference_between_the_two_readings(self):
        doc = frappe._dict(meter_reading_previous=1200, meter_reading_current=1450)
        _compute_meter_readings(doc)
        self.assertEqual(doc.meter_units_consumed, 250)

    def test_a_current_reading_below_the_previous_one_is_refused(self):
        doc = frappe._dict(meter_reading_previous=1450, meter_reading_current=1200)
        with self.assertRaises(frappe.ValidationError):
            _compute_meter_readings(doc)

    def test_a_first_bill_with_no_previous_reading_uses_the_whole_reading(self):
        doc = frappe._dict(meter_reading_previous=0, meter_reading_current=380)
        _compute_meter_readings(doc)
        self.assertEqual(doc.meter_units_consumed, 380)

    def test_equal_readings_consume_nothing_rather_than_refusing(self):
        doc = frappe._dict(meter_reading_previous=900, meter_reading_current=900)
        _compute_meter_readings(doc)
        self.assertEqual(doc.meter_units_consumed, 0)

    def test_consumption_keeps_three_decimals(self):
        doc = frappe._dict(meter_reading_previous=10.0005, meter_reading_current=20.0015)
        _compute_meter_readings(doc)
        self.assertEqual(doc.meter_units_consumed, round(20.0015 - 10.0005, 3))


class TestSharedMeterSplit(FrappeTestCase):

    def test_a_full_share_charges_the_whole_bill(self):
        doc = frappe._dict(total_bill_amount=1000, cost_bearing_pct=100)
        _compute_sharing(doc)
        self.assertEqual(doc.bill_amount, 1000)

    def test_a_partial_share_charges_only_that_percentage(self):
        doc = frappe._dict(total_bill_amount=1000, cost_bearing_pct=35)
        _compute_sharing(doc)
        self.assertEqual(doc.bill_amount, 350)

    def test_a_missing_percentage_means_the_whole_bill_not_nothing(self):
        for pct in (None, 0, ""):
            with self.subTest(pct=pct):
                doc = frappe._dict(total_bill_amount=1000, cost_bearing_pct=pct)
                _compute_sharing(doc)
                self.assertEqual(doc.bill_amount, 1000)

    def test_a_partial_share_explains_itself_on_the_document(self):
        doc = frappe._dict(total_bill_amount=1000, cost_bearing_pct=35)
        _compute_sharing(doc)
        self.assertTrue(doc.bill_share_note)
        self.assertIn("35", doc.bill_share_note)

    def test_a_full_share_leaves_no_note(self):
        doc = frappe._dict(total_bill_amount=1000, cost_bearing_pct=100)
        _compute_sharing(doc)
        self.assertEqual(doc.bill_share_note, "")

    def test_a_zero_invoice_computes_nothing(self):
        doc = frappe._dict(total_bill_amount=0, cost_bearing_pct=50, bill_amount=None)
        _compute_sharing(doc)
        self.assertIsNone(doc.bill_amount)
