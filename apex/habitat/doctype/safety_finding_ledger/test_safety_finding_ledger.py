# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

test_dependencies = ["Building"]


def _make_test_records(verbose=None):
    """Pin the test-record names so the live SFL- counter is never advanced."""
    from apex.tests._helpers import make_named_test_records

    return make_named_test_records("Safety Finding Ledger", "_T-SFL-")


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
