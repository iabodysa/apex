# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import getdate

from apex.habitat.doctype.lease.lease import _build_schedule


class TestLeasePaymentSchedule(FrappeTestCase):
    def _lease(self, **fields):
        doc = frappe.new_doc("Lease")
        doc.update(fields)
        return doc

    def test_a_lease_starting_on_the_31st_returns_to_the_31st_after_a_short_month(self):
        doc = self._lease(
            first_payment_date="2026-01-31",
            lease_end_date="2026-04-30",
            rent_amount=1000,
            billing_cycle="Monthly",
        )
        _build_schedule(doc)
        due_dates = [getdate(row.due_date) for row in doc.payment_schedule]
        self.assertEqual(
            due_dates,
            [
                getdate("2026-01-31"),
                getdate("2026-02-28"),
                getdate("2026-03-31"),
                getdate("2026-04-30"),
            ],
        )

    def test_every_scheduled_row_carries_the_monthly_rent_as_its_amount(self):
        doc = self._lease(
            first_payment_date="2026-01-01",
            lease_end_date="2026-03-01",
            rent_amount=1000,
            billing_cycle="Monthly",
        )
        _build_schedule(doc)
        self.assertTrue(doc.payment_schedule)
        for row in doc.payment_schedule:
            self.assertEqual(row.amount, 1000)

    def test_a_quarterly_cycle_bills_three_months_of_rent_per_row(self):
        doc = self._lease(
            first_payment_date="2026-01-01",
            lease_end_date="2026-01-01",
            rent_amount=1000,
            billing_cycle="Quarterly",
        )
        _build_schedule(doc)
        self.assertEqual(doc.payment_schedule[0].amount, 3000)

    def test_no_schedule_is_built_without_a_positive_rent_amount(self):
        doc = self._lease(
            first_payment_date="2026-01-01", lease_end_date="2026-06-01", rent_amount=0
        )
        _build_schedule(doc)
        self.assertFalse(doc.payment_schedule)

    def test_no_schedule_is_built_without_both_anchor_dates(self):
        doc = self._lease(
            first_payment_date="2026-01-01", lease_end_date=None, rent_amount=1000
        )
        _build_schedule(doc)
        self.assertFalse(doc.payment_schedule)

    def test_total_scheduled_sums_every_row_amount(self):
        doc = self._lease(
            first_payment_date="2026-01-01",
            lease_end_date="2026-03-01",
            rent_amount=500,
            billing_cycle="Monthly",
        )
        _build_schedule(doc)
        total = sum(row.amount for row in doc.payment_schedule)
        self.assertEqual(total, 500 * len(doc.payment_schedule))
