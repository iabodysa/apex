# Copyright (c) 2026, afmcoltd
"""Tests for Fuel Request's own arithmetic and per-type field guards.

Patterned on frappe/tests/test_document.py: each case builds an unsaved
Document via frappe.new_doc and calls one guard method directly. The quota
allowance guard takes its quota as a plain ``frappe._dict`` argument, so its
arithmetic is exercised without writing a Fuel Quota record at all.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase


class TestFuelRequest(FrappeTestCase):
    def _request(self, **fields):
        doc = frappe.new_doc("Fuel Request")
        doc.update(fields)
        return doc

    # -- _guard_quota_allowance: pure arithmetic, quota passed explicitly --

    def test_an_exhausted_quota_refuses_a_standard_draw(self):
        doc = self._request(fuel_quota="_Test Quota", requested_litres=5)
        quota = frappe._dict(consumed_litres=0, monthly_litres=10, status="Exhausted")
        self.assertRaises(frappe.ValidationError, doc._guard_quota_allowance, quota)

    def test_consumption_already_at_the_allocation_refuses_a_standard_draw(self):
        doc = self._request(fuel_quota="_Test Quota", requested_litres=1)
        quota = frappe._dict(consumed_litres=10, monthly_litres=10, status="Active")
        self.assertRaises(frappe.ValidationError, doc._guard_quota_allowance, quota)

    def test_an_oversized_first_draw_is_refused_even_at_zero_consumed(self):
        """15 L against a 10 L quota with 0 consumed must not pass on an
        exhaustion-only check: consumed < monthly is true, so the overrun is
        caught only by the second, draw-size comparison."""
        doc = self._request(fuel_quota="_Test Quota", requested_litres=15)
        quota = frappe._dict(consumed_litres=0, monthly_litres=10, status="Active")
        self.assertRaises(frappe.ValidationError, doc._guard_quota_allowance, quota)

    def test_a_draw_within_what_is_left_on_the_quota_is_accepted(self):
        doc = self._request(fuel_quota="_Test Quota", requested_litres=5)
        quota = frappe._dict(consumed_litres=3, monthly_litres=10, status="Active")
        doc._guard_quota_allowance(quota)

    def test_a_standard_request_with_no_linked_quota_is_not_graded(self):
        doc = self._request(requested_litres=1000)
        doc._guard_quota_allowance(
            frappe._dict(consumed_litres=0, monthly_litres=1, status="Active")
        )

    # -- per-type required-field validation --

    def test_standard_requires_positive_requested_litres(self):
        doc = self._request(request_type="Standard", requested_litres=0)
        self.assertRaises(frappe.ValidationError, doc._validate_standard)

    def test_standard_with_positive_litres_is_accepted(self):
        doc = self._request(request_type="Standard", requested_litres=10)
        doc._validate_standard()

    def test_topup_requires_positive_topup_litres(self):
        doc = self._request(
            request_type="Top-up", topup_litres=0, fuel_quota="_Test Quota"
        )
        self.assertRaises(frappe.ValidationError, doc._validate_topup)

    def test_topup_requires_a_linked_fuel_quota(self):
        doc = self._request(request_type="Top-up", topup_litres=5, fuel_quota=None)
        self.assertRaises(frappe.ValidationError, doc._validate_topup)

    def test_a_temporary_topup_requires_a_revert_due_date(self):
        doc = self._request(
            request_type="Top-up",
            topup_litres=5,
            fuel_quota="_Test Quota",
            is_temporary=1,
            revert_due_date=None,
        )
        self.assertRaises(frappe.ValidationError, doc._validate_topup)

    def test_a_non_temporary_topup_needs_no_revert_due_date(self):
        doc = self._request(
            request_type="Top-up",
            topup_litres=5,
            fuel_quota="_Test Quota",
            is_temporary=0,
        )
        doc._validate_topup()

    def test_a_chip_action_is_required(self):
        doc = self._request(request_type="Chip", action=None)
        self.assertRaises(frappe.ValidationError, doc._validate_chip)

    def test_replacing_a_chip_requires_its_chip_number(self):
        doc = self._request(request_type="Chip", action="Replace", chip_number=None)
        self.assertRaises(frappe.ValidationError, doc._validate_chip)

    def test_issuing_a_chip_needs_no_chip_number(self):
        doc = self._request(request_type="Chip", action="Issue", chip_number=None)
        doc._validate_chip()

    # -- initial-status guard and the approver stamp --

    def test_a_new_request_must_be_created_pending(self):
        doc = self._request(status="Approved")
        self.assertTrue(doc.is_new())
        self.assertRaises(frappe.ValidationError, doc._guard_initial_status)

    def test_a_new_request_left_at_pending_is_not_a_refusal(self):
        doc = self._request(status="Pending")
        doc._guard_initial_status()

    def test_approving_a_request_stamps_the_current_user_as_approver(self):
        doc = self._request(status="Approved", approved_by=None)
        doc._stamp_approver()
        self.assertEqual(doc.approved_by, frappe.session.user)

    def test_stamping_the_approver_does_not_override_one_already_set(self):
        doc = self._request(status="Approved", approved_by="someone@example.com")
        doc._stamp_approver()
        self.assertEqual(doc.approved_by, "someone@example.com")
