# Copyright (c) 2026, AFMCO and contributors
"""Fleet number-card guard: each Document Type card's metric stays wired to real fields.

A `type: "Document Type"` Number Card computes its metric by applying
`filters_json` (and, for Sum/Average, an aggregate field) against `document_type`.
If a filtered field or the aggregate field is renamed/removed on the DocType, the
card silently shows 0/blank with NO error. This locks two things down:

  PART 1 (structural) — every field named in a Salis card's `filters_json`, and the
  Sum/Average aggregate field, must still exist on its `document_type` meta.
  PART 2 (behavioural) — seeding one matching row moves the card's count by exactly 1,
  proving the shipped filter actually selects the data it claims to.

Open Theft Reports (the derived "stolen" card) is covered behaviourally in
salis/doctype/vehicle_incident/test_vehicle_incident.py, so it is not retested here.
Custom-card method resolution and dashboard-chart doc_type/based_on live in
tests/test_schema_integrity.py and are not duplicated.
"""

from __future__ import annotations

import glob
import json

import frappe
from frappe.model import default_fields, std_fields
from frappe.tests.utils import FrappeTestCase

APP = frappe.get_app_path("apex_habitat")

# Frappe injects these onto every DocType meta-side; never flag them as missing.
# std_fields is a list of {fieldname, fieldtype, label} dicts, so take the names.
STD_FIELDS = set(default_fields) | {f["fieldname"] for f in std_fields} | {"docstatus"}


def _salis_cards():
    """All Salis-module Number Card docs loaded from disk."""
    for j in sorted(glob.glob(f"{APP}/salis/number_card/*/*.json")):
        yield json.load(open(j, encoding="utf-8"))


def _filter_fieldnames(filters_json):
    """Yield the 2nd element (fieldname) of each [doctype, field, op, value] entry.

    `filters_json` is a JSON string; only the field is validated here, never the
    operator (Timespan / in / >= are all irrelevant to field existence).
    """
    for entry in json.loads(filters_json or "[]"):
        if isinstance(entry, (list, tuple)) and len(entry) >= 2:
            yield entry[1]


class TestFleetNumberCardsStructure(FrappeTestCase):
    def test_document_type_card_fields_exist(self):
        # Every filtered field (and Sum/Average aggregate field) on a
        # Document Type card must resolve on the card's document_type, else the
        # metric silently reads 0/blank.
        bad = []
        seen = set()
        for d in _salis_cards():
            if d.get("type") != "Document Type":
                continue  # Custom cards (e.g. Workshop Overstay) resolve via method, covered elsewhere.
            name, dt = d.get("name"), d.get("document_type")
            seen.add(name)
            if not dt or not frappe.db.exists("DocType", dt):
                bad.append(f"{name}: document_type {dt!r} missing")
                continue
            meta = frappe.get_meta(dt)
            for fld in _filter_fieldnames(d.get("filters_json")):
                if fld in STD_FIELDS:
                    continue
                if not meta.get_field(fld):
                    bad.append(f"{name}: filter field {dt}.{fld} missing")
            if d.get("function") in ("Sum", "Average"):
                agg = d.get("aggregate_function_based_on")
                if not agg or agg not in STD_FIELDS and not meta.get_field(agg):
                    bad.append(f"{name}: {d['function']} aggregate field {dt}.{agg!r} missing")
        # Non-vacuous: a known card must have been scanned, so a broken glob can't pass by checking nothing.
        self.assertIn("Active Vehicles", seen, "card scan found no Active Vehicles card; glob/path is broken")
        self.assertEqual(bad, [], f"Document Type cards referencing missing fields: {bad}")


class TestFleetNumberCardsBehaviour(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")

    def tearDown(self):
        frappe.set_user("Administrator")

    def _card_count(self, card_name):
        # Count exactly as the Fleet Operations dashboard does: read the shipped
        # card's own document_type + filters_json and apply them, so this fails if
        # the filter ever drifts from the status contract it depends on.
        card = frappe.get_doc("Number Card", card_name)
        return frappe.db.count(card.document_type, json.loads(card.filters_json or "[]"))

    def _vehicle(self, status):
        """A Salis Vehicle in `status`; plate keyed off the test method so it stays unique."""
        return frappe.get_doc(
            {
                "doctype": "Salis Vehicle",
                "plate_number": f"NC {self._testMethodName}",
                "status": status,
            }
        ).insert(ignore_permissions=True)

    def test_active_vehicles_card_counts_new_active_vehicle(self):
        # Active Vehicles filters Salis Vehicle status=Active.
        before = self._card_count("Active Vehicles")
        self._vehicle("Active")
        self.assertEqual(
            self._card_count("Active Vehicles"),
            before + 1,
            "the Active Vehicles card must count a newly created Active vehicle",
        )

    def test_under_maintenance_card_counts_new_maintenance_vehicle(self):
        # Vehicles Under Maintenance filters Salis Vehicle status=Under Maintenance.
        before = self._card_count("Vehicles Under Maintenance")
        self._vehicle("Under Maintenance")
        self.assertEqual(
            self._card_count("Vehicles Under Maintenance"),
            before + 1,
            "the Vehicles Under Maintenance card must count a newly created maintenance vehicle",
        )
