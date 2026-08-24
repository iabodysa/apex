# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

test_ignore = ["Project"]


class TestAuditRemediationPlanOverallStatus(FrappeTestCase):
    def test_a_past_deadline_with_an_open_item_rolls_the_plan_up_to_overdue(self):
        doc = frappe.get_doc(
            {
                "doctype": "Audit Remediation Plan",
                "naming_series": "CARP-.YYYY.-.####",
                "client_project": "_T-Audit-Project-fake",
                "audit_received_date": "2026-01-01",
                "remediation_deadline": "2026-01-10",
                "remediation_items": [
                    {
                        "finding_description": "_T-Missing extinguisher tag",
                        "remediation_action": "_T-Retag extinguishers",
                        "due_date": "2026-01-05",
                        "status": "Open",
                    }
                ],
            }
        )
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.addCleanup(
            lambda name=doc.name: frappe.delete_doc(
                "Audit Remediation Plan", name, ignore_permissions=True, force=True
            )
        )
        self.assertEqual(doc.overall_status, "Overdue")
