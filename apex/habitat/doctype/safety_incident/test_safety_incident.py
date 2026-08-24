# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

test_dependencies = ["Building"]


class TestSafetyIncidentCloseGuard(FrappeTestCase):
    def test_closing_without_resolution_notes_is_refused(self):
        doc = frappe.get_doc(
            {
                "doctype": "Safety Incident",
                "naming_series": "HSI-.YYYY.-.#####",
                "incident_datetime": "2026-01-10 08:00:00",
                "building": "_Test Building",
                "severity": "Low",
                "description": "_T-Safety Incident guard",
                "status": "Closed",
            }
        )
        with self.assertRaises(frappe.ValidationError):
            doc.insert(ignore_permissions=True)
