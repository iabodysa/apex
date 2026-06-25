# Copyright (c) 2026, AFMCO and contributors
"""Arrival Batch tests: the pre-arrival manifest. Each case provisions its own
building, supplier, and batch so asserts are exact regardless of pre-existing
site data. Confirms the schema contract get_arrival_summary relies on
(building, expected_date, expected_count) and the Temporary Worker.arrival_batch
Link, then exercises manifest-completion telemetry end to end."""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex_habitat.habitat.api.arrivals_desk import get_arrival_summary


def _h(n=6):
    return frappe.generate_hash(length=n).upper()


class TestArrivalBatch(FrappeTestCase):
    def setUp(self):
        self.date = "2026-07-01"
        # A bare building string (not a real Accommodation Building) so the
        # assignment controller's project/cost-center gates bail early — the same
        # direct approach the sibling get_arrival_summary tests use. The Arrival
        # Batch Link is inserted with ignore_links for the same reason.
        self.building = "BLDG-" + _h()
        self.supplier = frappe.get_doc({
            "doctype": "Supplier",
            "supplier_name": "SUP-" + _h(),
            "supplier_group": frappe.db.get_value("Supplier Group", {}, "name"),
        }).insert(ignore_permissions=True, ignore_if_duplicate=True).name

    def _batch(self, rows):
        doc = frappe.get_doc({
            "doctype": "Arrival Batch",
            "building": self.building,
            "expected_date": self.date,
            "labour_supplier": self.supplier,
            "expected_workers": [{"worker_name": w, "passport_number": "P" + _h(8)} for w in rows],
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        return doc

    def test_expected_count_computed_from_rows(self):
        """expected_count is derived from the manifest rows, not entered by hand."""
        doc = self._batch(["A", "B", "C"])
        self.assertEqual(doc.expected_count, 3)
        # A title is stamped for the list/link display.
        self.assertTrue(doc.title)

    def test_empty_manifest_is_rejected(self):
        """A batch with no expected workers is meaningless and must not save."""
        doc = frappe.get_doc({
            "doctype": "Arrival Batch",
            "building": self.building,
            "expected_date": self.date,
            "expected_workers": [],
        })
        self.assertRaises(frappe.ValidationError, doc.insert,
                          ignore_permissions=True, ignore_links=True)

    def test_temporary_worker_links_to_arrival_batch(self):
        """The Temporary Worker.arrival_batch field is a Link onto Arrival Batch
        (the schema half of the manifest reconciliation)."""
        meta = frappe.get_meta("Temporary Worker")
        field = meta.get_field("arrival_batch")
        self.assertIsNotNone(field, "Temporary Worker.arrival_batch exists")
        self.assertEqual(field.fieldtype, "Link")
        self.assertEqual(field.options, "Arrival Batch")

    def test_manifest_completion_measured_against_batch(self):
        """With a batch on the date and N housed arrivals, get_arrival_summary
        reports the expected count and a completion percentage (no longer None)."""
        self._batch(["A", "B", "C", "D"])  # expected 4

        # Two real housed arrivals on the date in this building.
        for _i in range(2):
            asgn = frappe.get_doc({
                "doctype": "Accommodation Assignment",
                "naming_series": "ACC-ASGN-.YYYY.-.####",
                "party_type": "Employee",
                "party": "EMP-" + _h(),
                "employee": "EMP-" + _h(),
                "building": self.building,
            }).insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
            frappe.db.set_value("Accommodation Assignment", asgn.name,
                                {"docstatus": 1, "check_in_date": self.date},
                                update_modified=False)

        r = get_arrival_summary(date=self.date, building=self.building)
        self.assertEqual(r["manifest_expected"], 4)
        self.assertEqual(r["manifest_completion_pct"], 50.0)
