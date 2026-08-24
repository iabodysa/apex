# Copyright (c) 2026, afmcoltd
"""Tests for Accommodation Ledger's party-to-employee mirroring.

Patterned on frappe/tests/test_document.py. The row is built directly and
inserted so ``before_save`` in ``accommodation_ledger.py`` -- wired through
hooks.py's doc_events, not the class body -- is what is exercised, not a
stub. The mirror direction is pinned by apex/habitat/api/custody_kiosk.py's
own docstring: an Employee party mirrors onto the ``employee`` column.

``Project`` is excluded from the dependency walk: no case here sets it, and
its own closure reaches Purchase Invoice's neighbourhood, which resolves an
unmigrated ``Payment Gateway`` and kills record-building before a single
test runs.
"""

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
