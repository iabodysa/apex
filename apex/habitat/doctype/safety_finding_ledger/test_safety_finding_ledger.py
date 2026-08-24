# Copyright (c) 2026, afmcoltd
"""Tests for Safety Finding Ledger's immutability and delete refusal.

Patterned on frappe/tests/test_document.py. Every case crosses
``insert``/``save``/``delete`` so the two ``on_update``/``on_trash`` guards in
``safety_finding_ledger.py`` are what is exercised, not a stub. No role holds
delete on this DocType's own DocPerm, so ``on_trash`` refuses everyone
outside install/migrate -- Administrator included, unlike Cleaning Compliance
Ledger's System-Manager carve-out.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

test_dependencies = ["Building"]


class TestSafetyFindingLedgerImmutability(FrappeTestCase):
    def _row(self, **fields):
        data = {
            "doctype": "Safety Finding Ledger",
            "posting_date": "2026-01-10",
            "building": "_Test Building",
            "finding": "_T-Smoke detector missing in corridor",
            "severity": "High",
            "status": "Open",
        }
        data.update(fields)
        doc = frappe.get_doc(data)
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.addCleanup(
            lambda name=doc.name: frappe.db.delete(
                "Safety Finding Ledger", {"name": name}
            )
        )
        return doc

    def test_editing_a_posted_row_after_insert_is_refused(self):
        doc = self._row()
        doc.resolved = 1
        with self.assertRaises(frappe.ValidationError):
            doc.save(ignore_permissions=True)

    def test_deleting_a_posted_row_is_refused_even_for_the_administrator(self):
        doc = self._row()
        with self.assertRaises(frappe.ValidationError):
            frappe.delete_doc(
                "Safety Finding Ledger", doc.name, ignore_permissions=True
            )
