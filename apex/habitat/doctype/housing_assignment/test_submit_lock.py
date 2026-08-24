# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase


class TestTermsConsentIsSubmitLocked(FrappeTestCase):
    def _submitted_assignment(self):
        name = frappe.db.get_value(
            "Housing Assignment",
            {
                "docstatus": 1,
                "room": ("is", "set"),
                "bed": ("is", "set"),
                "project": ("is", "set"),
            },
            "name",
            order_by="creation asc",
        )
        if not name:
            doc = frappe.get_doc(frappe.get_test_records("Housing Assignment")[0])
            doc.insert()
            doc.submit()
            name = doc.name
        return frappe.get_doc("Housing Assignment", name)

    def test_the_signature_cannot_be_replaced_after_submit(self):
        doc = self._submitted_assignment()
        doc.terms_signature = "data:image/png;base64,AAAA"
        with self.assertRaises(frappe.UpdateAfterSubmitError):
            doc.save()

    def test_the_acceptance_stamp_cannot_be_moved_after_submit(self):
        doc = self._submitted_assignment()
        doc.terms_accepted_on = "2026-01-01 00:00:00"
        with self.assertRaises(frappe.UpdateAfterSubmitError):
            doc.save()
