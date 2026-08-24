# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

test_dependencies = ["Supplier"]


class TestSubcontractorServiceContractDateGuard(FrappeTestCase):
    def test_an_end_date_before_the_start_date_is_refused(self):
        doc = frappe.get_doc(
            {
                "doctype": "Subcontractor Service Contract",
                "supplier": "_Test Supplier",
                "naming_series": "SUB-CON-.YYYY.-.####",
                "service_type": "Pest Control",
                "contract_start_date": "2026-06-01",
                "contract_end_date": "2026-01-01",
            }
        )
        with self.assertRaises(frappe.ValidationError):
            doc.insert(ignore_permissions=True)
