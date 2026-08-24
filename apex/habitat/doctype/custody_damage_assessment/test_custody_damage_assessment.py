# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.habitat.doctype.custody_damage_assessment.custody_damage_assessment import (
    _stamp_acknowledgement,
    _stamp_signoff,
    validate,
)


class TestStampSignoff(FrappeTestCase):
    def _doc(self, **fields):
        doc = frappe.new_doc("Custody Damage Assessment")
        doc.update(fields)
        return doc

    def test_a_draft_carries_no_assessor(self):
        doc = self._doc(status="Draft", assessed_by="someone@example.com")
        _stamp_signoff(doc)
        self.assertIsNone(doc.assessed_by)

    def test_leaving_draft_stamps_the_current_user_as_assessor(self):
        doc = self._doc(status="Pending Approval", assessed_by=None)
        _stamp_signoff(doc)
        self.assertEqual(doc.assessed_by, frappe.session.user)

    def test_an_already_stamped_assessor_is_never_overwritten(self):
        doc = self._doc(status="Pending Approval", assessed_by="original@example.com")
        _stamp_signoff(doc)
        self.assertEqual(doc.assessed_by, "original@example.com")

    def test_reaching_approved_stamps_the_approver_and_date(self):
        doc = self._doc(status="Approved", approved_by=None, approved_on=None)
        _stamp_signoff(doc)
        self.assertEqual(doc.approved_by, frappe.session.user)
        self.assertIsNotNone(doc.approved_on)

    def test_leaving_approved_drops_the_approver_and_date(self):
        doc = self._doc(
            status="Rejected", approved_by="approver@example.com", approved_on="2026-01-01"
        )
        _stamp_signoff(doc)
        self.assertIsNone(doc.approved_by)
        self.assertIsNone(doc.approved_on)


class TestStampAcknowledgement(FrappeTestCase):
    def _doc(self, **fields):
        doc = frappe.new_doc("Custody Damage Assessment")
        doc.update(fields)
        return doc

    def test_a_fresh_signature_is_dated(self):
        doc = self._doc(worker_signature="data:image/png;base64,AAA", acknowledged_on=None)
        _stamp_acknowledgement(doc)
        self.assertIsNotNone(doc.acknowledged_on)

    def test_an_already_dated_signature_keeps_its_original_date(self):
        doc = self._doc(
            worker_signature="data:image/png;base64,AAA",
            acknowledged_on="2026-01-01 00:00:00",
        )
        _stamp_acknowledgement(doc)
        self.assertEqual(str(doc.acknowledged_on), "2026-01-01 00:00:00")

    def test_removing_the_signature_clears_the_acknowledgement_date(self):
        doc = self._doc(worker_signature=None, acknowledged_on="2026-01-01 00:00:00")
        _stamp_acknowledgement(doc)
        self.assertIsNone(doc.acknowledged_on)


class TestValidateTotalsReplacementCost(FrappeTestCase):
    def test_the_total_is_the_sum_of_every_items_estimated_cost(self):
        doc = frappe.new_doc("Custody Damage Assessment")
        doc.append("items", {"estimated_replacement_cost": 300})
        doc.append("items", {"estimated_replacement_cost": 450.5})
        validate(doc)
        self.assertEqual(doc.total_estimated_replacement_cost, 750.5)
