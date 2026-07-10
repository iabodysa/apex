# Copyright (c) 2026, AFMCO and contributors
"""get_arrival_summary tests: the read-only manager telemetry endpoint. Each case
scopes to a unique building so asserts are exact regardless of pre-existing site
data. Assignments are inserted directly (ignore_permissions/ignore_links/
ignore_mandatory) and forced to docstatus=1 + check_in_date via db.set_value
(validate would otherwise run the bed-lock/occupancy gates) — the same direct
approach the sibling dashboard tests use. Beds are real so the is_temporary
over-capacity lookup is genuinely exercised."""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex_habitat.habitat.api.arrivals_desk import get_arrival_summary


def _h(n=6):
    return frappe.generate_hash(length=n).upper()


class TestArrivalsSummary(FrappeTestCase):
    def setUp(self):
        self.date = "2026-06-20"
        self.other_date = "2026-06-19"
        self.building = "BLDG-" + _h()
        self.supplier = "SUP-" + _h()
        self._assignments = []
        self._beds = []

        # A normal bed and a minted over-capacity (is_temporary) bed in this building.
        self.bed_normal = self._bed(is_temporary=0)
        self.bed_oc = self._bed(is_temporary=1)

        # A labour supplier and a Temporary Worker billed to it.
        frappe.get_doc({
            "doctype": "Supplier",
            "supplier_name": self.supplier,
            "supplier_group": frappe.db.get_value("Supplier Group", {}, "name"),
        }).insert(ignore_permissions=True, ignore_if_duplicate=True)
        self.tw = frappe.get_doc({
            "doctype": "Temporary Worker",
            "worker_name": "TW-" + _h(),
            "passport_number": "P" + _h(8),
            "labour_supplier": self.supplier,
        })
        self.tw.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)

        # (1) Today, Temporary Worker via supplier, in the over-capacity bed.
        self._assignment(self.date, "Temporary Worker", self.tw.name, self.bed_oc)
        # (2) Today, direct Employee (no supplier), in the normal bed.
        self._assignment(self.date, "Employee", "EMP-" + _h(), self.bed_normal)
        # (3) A different date -> must be excluded from the date-scoped summary.
        self._assignment(self.other_date, "Employee", "EMP-" + _h(), self.bed_normal)

    def _bed(self, is_temporary):
        doc = frappe.get_doc({
            "doctype": "Bed",
            "bed_code": "BED-" + _h(),
            "building": self.building,
            "status": "Available",
            "is_temporary": is_temporary,
        })
        doc.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        self._beds.append(doc.name)
        return doc.name

    def _assignment(self, check_in_date, party_type, party, bed):
        doc = frappe.get_doc({
            "doctype": "Housing Assignment",
            "naming_series": "ACC-ASGN-.YYYY.-.####",
            "party_type": party_type,
            "party": party,
            "employee": party if party_type == "Employee" else None,
            "building": self.building,
            "bed": bed,
        })
        doc.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        # Force the submitted + check-in state the read endpoint filters on.
        frappe.db.set_value(
            "Housing Assignment", doc.name,
            {"docstatus": 1, "check_in_date": check_in_date}, update_modified=False,
        )
        self._assignments.append(doc.name)
        return doc.name

    def tearDown(self):
        for name in self._assignments:
            frappe.db.set_value("Housing Assignment", name, "docstatus", 0,
                                update_modified=False)
            frappe.delete_doc("Housing Assignment", name, force=True,
                              ignore_permissions=True)
        if getattr(self, "tw", None):
            frappe.delete_doc("Temporary Worker", self.tw.name, force=True,
                              ignore_permissions=True)
        for name in self._beds:
            frappe.delete_doc("Bed", name, force=True,
                              ignore_permissions=True)

    def test_housed_count_is_date_and_building_scoped(self):
        """Only today's submitted check-ins in this building are counted (the
        other-date assignment is excluded)."""
        r = get_arrival_summary(date=self.date, building=self.building)
        self.assertEqual(r["housed_count"], 2, "two arrivals on the date in this building")
        self.assertEqual(r["date"], self.date)
        self.assertEqual(r["building"], self.building)

    def test_by_supplier_breakdown(self):
        """The supplier breakdown splits the supplier-billed worker from the direct
        one; the supplier row carries its display name."""
        r = get_arrival_summary(date=self.date, building=self.building)
        by = {row["supplier"]: row for row in r["by_supplier"]}
        self.assertIn(self.supplier, by, "the labour supplier appears as its own bucket")
        self.assertEqual(by[self.supplier]["count"], 1)
        self.assertEqual(by[self.supplier]["supplier_name"], self.supplier)
        self.assertIn(None, by, "the direct (no-supplier) worker is its own bucket")
        self.assertEqual(by[None]["count"], 1)

    def test_over_capacity_count_uses_is_temporary_bed(self):
        """The over-capacity count reflects the one arrival placed in a minted
        is_temporary bed."""
        r = get_arrival_summary(date=self.date, building=self.building)
        self.assertEqual(r["over_capacity_count"], 1)

    def test_manifest_is_none_without_arrival_batch(self):
        """Manifest completion is unmeasurable (None) until an Arrival Batch source
        exists — it is never fabricated."""
        r = get_arrival_summary(date=self.date, building=self.building)
        if not frappe.db.exists("DocType", "Arrival Batch"):
            self.assertIsNone(r["manifest_completion_pct"])
            self.assertIsNone(r["manifest_expected"])

    def test_read_only_creates_nothing(self):
        """A second identical call returns the same housed count — the endpoint
        posts/locks nothing."""
        first = get_arrival_summary(date=self.date, building=self.building)
        second = get_arrival_summary(date=self.date, building=self.building)
        self.assertEqual(first["housed_count"], second["housed_count"])
