# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

test_dependencies = ["Building", "Employee"]
test_ignore = ["Project"]


class TestAccommodationLedgerPartyMirroring(FrappeTestCase):
    def test_an_employee_party_is_mirrored_onto_the_employee_column(self):
        doc = frappe.get_doc(
            {
                "doctype": "Accommodation Ledger",
                "posting_date": "2026-01-15",
                "ledger_type": "Rent",
                "building": "_Test Building",
                "party_type": "Employee",
                "party": "_T-Employee-00001",
            }
        )
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.addCleanup(
            lambda name=doc.name: frappe.db.delete("Accommodation Ledger", {"name": name})
        )
        self.assertEqual(doc.employee, "_T-Employee-00001")
