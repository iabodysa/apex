# Copyright (c) 2026, afmcoltd
"""Accommodation Ledger's own contract: a row needs a posting date, a building and a ledger type.

The building comes from ``test_records.json``, so the link is really checked, rather than a
``QA-BLDG`` name that exists on no site with ``ignore_links=True`` passed to stop Frappe noticing,
or a sixteen-line ``test_ignore`` block for masters the ledger does not link to.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

test_dependencies = ["Building"]

BUILDING = "_Test Building"


class TestAccommodationLedger(FrappeTestCase):
    def _row(self, **overrides):
        payload = {
            "doctype": "Accommodation Ledger",
            "posting_date": "2026-06-01",
            "building": BUILDING,
            "ledger_type": "Rent",
        }
        payload.update(overrides)
        return frappe.get_doc(payload)

    def test_a_row_takes_the_ledger_type_it_is_given(self):
        row = self._row()
        row.insert(ignore_permissions=True)
        self.addCleanup(
            frappe.delete_doc, "Accommodation Ledger", row.name, force=True, ignore_permissions=True
        )

        self.assertEqual(row.ledger_type, "Rent")
        self.assertEqual(row.building, BUILDING)

    def test_a_row_without_a_posting_date_is_refused(self):
        row = self._row(posting_date=None, ledger_type="Electricity")

        with self.assertRaises(frappe.exceptions.MandatoryError):
            row.insert(ignore_permissions=True)

    def test_a_row_saved_without_a_ledger_type_silently_takes_the_first_one(self):
        """A required Select left empty is not caught by the mandatory check.

        ``ledger_type`` is a required Select, and Frappe fills a required Select with the FIRST of
        its options when it is left empty — so the mandatory pass never fires and the row is
        classified for the operator rather than by him.
        """
        row = self._row(ledger_type=None)
        row.insert(ignore_permissions=True)
        self.addCleanup(
            frappe.delete_doc, "Accommodation Ledger", row.name, force=True, ignore_permissions=True
        )

        first_option = frappe.get_meta("Accommodation Ledger").get_field("ledger_type").options.split("\n")[0]
        self.assertEqual(row.ledger_type, first_option)
