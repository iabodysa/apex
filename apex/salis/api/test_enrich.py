# Copyright (c) 2026, AFMCO and contributors
"""Tests for the shared vehicle/driver bulk title-enrichment helper.

Asserts the docstring's contract: ``vehicle_plate`` + ``driver_name`` are attached
to every row in place (two bounded lookups, no N+1), the plate/name fall back to
the raw docname when a title is missing, custom field names are honoured, and the
same ``rows`` object is returned.
"""

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.salis.api.enrich import vehicle_driver_titles


def _vehicle(plate):
    return frappe.get_doc(
        {"doctype": "Salis Vehicle", "plate_number": plate, "status": "Active"}
    ).insert(ignore_permissions=True).name


def _driver(name):
    return frappe.get_doc(
        {"doctype": "Salis Driver", "full_name": name, "status": "Active"}
    ).insert(ignore_permissions=True).name


class TestVehicleDriverTitles(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        tag = frappe.generate_hash(length=12)
        self.vehicle = _vehicle(f"ENR-{tag}")
        self.driver = _driver(f"Enrich Driver {tag}")
        self.addCleanup(self._purge)

    def _purge(self):
        frappe.set_user("Administrator")
        frappe.delete_doc("Salis Vehicle", self.vehicle, force=True, ignore_permissions=True)
        frappe.delete_doc("Salis Driver", self.driver, force=True, ignore_permissions=True)

    def test_attaches_plate_and_driver_name_in_place(self):
        rows = [{"vehicle": self.vehicle, "driver": self.driver}]
        returned = vehicle_driver_titles(rows)

        # The function rebuilds the outer list (``rows = list(rows)``) but mutates
        # each row dict in place, so the returned rows are the SAME row objects.
        self.assertIs(returned[0], rows[0], "each row must be enriched in place")
        plate = frappe.db.get_value("Salis Vehicle", self.vehicle, "plate_number")
        full_name = frappe.db.get_value("Salis Driver", self.driver, "full_name")
        self.assertEqual(rows[0]["vehicle_plate"], plate)
        self.assertEqual(rows[0]["driver_name"], full_name)

    def test_falls_back_to_docname_when_reference_is_unknown(self):
        rows = [{"vehicle": "NO-SUCH-VEHICLE", "driver": "NO-SUCH-DRIVER"}]
        vehicle_driver_titles(rows)

        self.assertEqual(rows[0]["vehicle_plate"], "NO-SUCH-VEHICLE")
        self.assertEqual(rows[0]["driver_name"], "NO-SUCH-DRIVER")

    def test_missing_reference_yields_falsy_title(self):
        rows = [{}]
        vehicle_driver_titles(rows)

        self.assertFalse(rows[0]["vehicle_plate"])
        self.assertFalse(rows[0]["driver_name"])

    def test_honours_custom_field_names(self):
        rows = [{"assigned_vehicle": self.vehicle, "assigned_driver": self.driver}]
        vehicle_driver_titles(rows, vehicle_field="assigned_vehicle", driver_field="assigned_driver")

        plate = frappe.db.get_value("Salis Vehicle", self.vehicle, "plate_number")
        full_name = frappe.db.get_value("Salis Driver", self.driver, "full_name")
        self.assertEqual(rows[0]["vehicle_plate"], plate)
        self.assertEqual(rows[0]["driver_name"], full_name)

    def test_resolves_in_two_bounded_queries_regardless_of_row_count(self):
        rows = [{"vehicle": self.vehicle, "driver": self.driver} for _ in range(5)]
        with patch.object(frappe, "get_all", wraps=frappe.get_all) as spy:
            vehicle_driver_titles(rows)
        self.assertEqual(spy.call_count, 2, "must resolve titles in exactly two bounded lookups")
