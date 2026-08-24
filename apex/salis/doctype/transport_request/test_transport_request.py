# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase


class TestTransportRequestIsAssignedIsFrozenAfterSubmit(FrappeTestCase):
    def _submitted_request(self):
        doc = frappe.new_doc("Transport Request")
        doc.service_line = "Administrative Trip"
        doc.request_type = "Administrative Trip / Document Signing"
        doc.destination = "Riyadh Head Office"
        doc.requested_by = "Administrator"
        doc.insert()
        doc.submit()
        return doc

    def test_editing_is_assigned_after_submit_is_refused(self):
        doc = self._submitted_request()
        doc.is_assigned = 1
        self.assertRaises(frappe.exceptions.UpdateAfterSubmitError, doc.save)
