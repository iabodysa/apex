# Copyright (c) 2026, afmcoltd
"""Tests for Cleaning Compliance Ledger's immutability guards.

Patterned on frappe/tests/test_document.py for a write-once, no-trash record.
Every row crosses ``insert``/``save``/``delete`` so the doc_events guards in
``cleaning_compliance_ledger.py`` are what is exercised, not a stub.

``Cleaning Log`` is excluded from the dependency walk: no case here sets it,
and its own link field to Subcontractor Service Order reaches Purchase
Invoice's ERPNext closure, which resolves an unmigrated ``Payment Gateway``
and kills record-building before a single test runs.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.tests._helpers import _user

test_dependencies = ["Building"]
test_ignore = ["Cleaning Log"]


class TestCleaningComplianceLedgerImmutability(FrappeTestCase):
    def _row(self, **fields):
        data = {
            "doctype": "Cleaning Compliance Ledger",
            "posting_date": "2026-01-10",
            "building": "_Test Building",
            "room": "_T-101",
            "cleaned": 1,
        }
        data.update(fields)
        doc = frappe.get_doc(data)
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.addCleanup(
            lambda name=doc.name: frappe.db.delete(
                "Cleaning Compliance Ledger", {"name": name}
            )
        )
        return doc

    def test_editing_a_posted_row_after_insert_is_refused(self):
        doc = self._row()
        doc.cleaned = 0
        with self.assertRaises(frappe.ValidationError):
            doc.save(ignore_permissions=True)

    def test_deleting_a_posted_row_without_the_system_manager_role_is_refused(self):
        doc = self._row()
        email = _user("cclviewer@example.com", "Accommodation Manager")
        with self.set_user(email):
            with self.assertRaises(frappe.ValidationError):
                frappe.delete_doc(
                    "Cleaning Compliance Ledger", doc.name, ignore_permissions=True
                )
