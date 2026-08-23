# Copyright (c) 2026, afmcoltd

"""Meter arithmetic and the shared-meter split, on a bill nobody can re-read later.

A utility bill is entered once from paper and its derived figures are what every later
report uses, so an error here is invisible: the number looks like a number.

WHY ``test_ignore`` IS SET AND WHY IT IS NOT A WORKAROUND. ``get_dependencies``
(frappe/test_runner.py:359-381) collects every Link field on the DocType under test AND
every Link on its child tables, then builds a test record for each — whether or not any
test touches them. This DocType Links to ``Payment Entry``, whose own graph reaches
``Payment Gateway`` through Payment Entry Reference and Payment Request; the payments app
is on the bench but NOT installed on this site, so collecting that chain aborts the whole
suite before a single test runs — measured, not assumed.

``test_ignore`` is the framework's own escape hatch for exactly this, read at
frappe/test_runner.py:374-377 from the test module of the DocType under test, so it is
scoped to this file and changes nothing for any other DocType. It is honest here because
none of these tests touches the payment link: they exercise pure arithmetic on an unsaved
document. A test that DID need the payment link could not use this and would have to wait
for the payments app.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.habitat.doctype.utility_bill_entry.utility_bill_entry import (
    _compute_meter_readings,
    _compute_sharing,
)

test_ignore = ["Payment Entry"]


class TestMeterReadings(FrappeTestCase):
    """Consumption is derived, never typed, so the derivation must be exact."""

    def test_consumption_is_the_difference_between_the_two_readings(self):
        doc = frappe._dict(meter_reading_previous=1200, meter_reading_current=1450)
        _compute_meter_readings(doc)
        self.assertEqual(doc.meter_units_consumed, 250)

    def test_a_current_reading_below_the_previous_one_is_refused(self):
        """A meter does not run backwards; accepting it would post a negative
        consumption and a negative cost against the building."""
        doc = frappe._dict(meter_reading_previous=1450, meter_reading_current=1200)
        with self.assertRaises(frappe.ValidationError):
            _compute_meter_readings(doc)

    def test_a_first_bill_with_no_previous_reading_uses_the_whole_reading(self):
        doc = frappe._dict(meter_reading_previous=0, meter_reading_current=380)
        _compute_meter_readings(doc)
        self.assertEqual(doc.meter_units_consumed, 380)

    def test_equal_readings_consume_nothing_rather_than_refusing(self):
        """A month with no consumption is a real month, not an error."""
        doc = frappe._dict(meter_reading_previous=900, meter_reading_current=900)
        _compute_meter_readings(doc)
        self.assertEqual(doc.meter_units_consumed, 0)

    def test_consumption_keeps_three_decimals(self):
        doc = frappe._dict(meter_reading_previous=10.0005, meter_reading_current=20.0015)
        _compute_meter_readings(doc)
        self.assertEqual(doc.meter_units_consumed, round(20.0015 - 10.0005, 3))


class TestSharedMeterSplit(FrappeTestCase):
    """When one meter serves several buildings, this decides what each one pays."""

    def test_a_full_share_charges_the_whole_bill(self):
        doc = frappe._dict(total_bill_amount=1000, cost_bearing_pct=100)
        _compute_sharing(doc)
        self.assertEqual(doc.bill_amount, 1000)

    def test_a_partial_share_charges_only_that_percentage(self):
        doc = frappe._dict(total_bill_amount=1000, cost_bearing_pct=35)
        _compute_sharing(doc)
        self.assertEqual(doc.bill_amount, 350)

    def test_a_missing_percentage_means_the_whole_bill_not_nothing(self):
        """The defect this guards: an unset percentage read as zero would charge the
        building nothing and silently move the cost nowhere."""
        for pct in (None, 0, ""):
            with self.subTest(pct=pct):
                doc = frappe._dict(total_bill_amount=1000, cost_bearing_pct=pct)
                _compute_sharing(doc)
                self.assertEqual(doc.bill_amount, 1000)

    def test_a_partial_share_explains_itself_on_the_document(self):
        """The operator must be able to see WHY the figure is not the invoice total."""
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
