# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase


class TestCustodyAcknowledgmentRequiresSubmittedIssue(FrappeTestCase):
    def test_acknowledging_an_unsubmitted_custody_issue_is_refused(self):
        doc = frappe.get_doc(
            {
                "doctype": "Custody Acknowledgment",
                "custody_issue": "_T-CACK-nonexistent-issue",
                "confirmation_method": "Confirmed Receipt",
                "receipt_confirmed": 1,
            }
        )
        with self.assertRaises(frappe.ValidationError):
            doc.insert(ignore_permissions=True, ignore_links=True)
