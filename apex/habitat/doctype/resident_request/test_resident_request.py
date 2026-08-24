# Copyright (c) 2026, afmcoltd
"""Tests for Resident Request's honeypot refusal and its close-without-notes guard.

Patterned on frappe/tests/test_document.py. Every case crosses ``insert`` so
``validate`` in ``resident_request.py`` -- wired through hooks.py's
doc_events, not the class body -- is what is exercised, not a stub.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase


class TestResidentRequestGuards(FrappeTestCase):
    def _request(self, **fields):
        data = {
            "doctype": "Resident Request",
            "naming_series": "REQ-.YYYY.-.####",
            "request_category": "Maintenance",
            "description": "_T-Resident Request guard",
        }
        data.update(fields)
        return frappe.get_doc(data)

    def test_a_filled_honeypot_field_is_refused(self):
        doc = self._request(website_field="bot-filled")
        with self.assertRaises(frappe.PermissionError):
            doc.insert(ignore_permissions=True)

    def test_closing_without_resolution_notes_is_refused(self):
        doc = self._request(status="Closed")
        with self.assertRaises(frappe.ValidationError):
            doc.insert(ignore_permissions=True)
