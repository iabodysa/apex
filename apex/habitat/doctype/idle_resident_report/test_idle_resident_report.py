# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

test_dependencies = ["Building", "Employee"]


class TestIdleResidentReportStatusGuard(FrappeTestCase):
    def test_resolving_without_resolution_notes_is_refused(self):
        doc = frappe.get_doc(
            {
                "doctype": "Idle Resident Report",
                "naming_series": "IDLE-.YYYY.-.####",
                "party_type": "Employee",
                "employee": "_T-Employee-00001",
                "building": "_Test Building",
                "reason_category": "New Hire",
                "responsible_department": "HR",
                "reported_on": "2026-01-10",
                "status": "Resolved",
            }
        )
        with self.assertRaises(frappe.ValidationError):
            doc.insert(ignore_permissions=True)
