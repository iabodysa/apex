# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

test_ignore = ["Purchase Invoice"]


class TestSubcontractorServiceOrderLineAmounts(FrappeTestCase):
    def test_a_lines_amount_is_computed_from_qty_times_rate(self):
        doc = frappe.get_doc(
            {
                "doctype": "Subcontractor Service Order",
                "building": "_Test Building",
                "scheduled_date": "2026-03-01",
                "contract": "_T-SSC-nonexistent",
                "naming_series": "SSO-.YYYY.-.#####",
                "service_items": [
                    {"description": "Visit", "qty": 2, "rate": 100},
                ],
            }
        )
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.addCleanup(
            lambda name=doc.name: frappe.delete_doc(
                "Subcontractor Service Order", name, ignore_permissions=True, force=True
            )
        )
        self.assertEqual(doc.service_items[0].amount, 200)
