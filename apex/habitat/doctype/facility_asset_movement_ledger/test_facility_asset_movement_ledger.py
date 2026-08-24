# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

test_dependencies = ["Building"]
test_ignore = ["Facility Asset"]


class TestFacilityAssetMovementLedgerImmutability(FrappeTestCase):
    def _row(self, **fields):
        data = {
            "doctype": "Facility Asset Movement Ledger",
            "posting_datetime": "2026-01-10 08:00:00",
            "from_building": "_Test Building",
            "to_building": "_Test Building 2",
            "source_doctype": "Facility Asset Movement",
            "source_name": "_T-FAM-9001",
        }
        data.update(fields)
        doc = frappe.get_doc(data)
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.addCleanup(
            lambda name=doc.name: frappe.db.delete(
                "Facility Asset Movement Ledger", {"name": name}
            )
        )
        return doc

    def test_editing_a_posted_row_after_insert_is_refused(self):
        doc = self._row()
        doc.to_location = "Rewritten"
        with self.assertRaises(frappe.PermissionError):
            doc.save(ignore_permissions=True)
