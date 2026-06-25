"""Tests for the Fleet Control export.

``export_fleet`` re-runs the scoped board query server-side and streams it as a
native csv response, so the file holds the FULL permission-/scope-consistent
result rather than only the rows a client happened to paint. The project-scope
resolver is patched so the export's scope can be asserted deterministically on a
fresh site.
"""

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from apex_habitat.salis.api import operations_control

# get_fleet resolves scope through the shared fleet_reader service, so the
# project-scope resolver is patched there (its single home).
_RESOLVER = "apex_habitat.salis.api.fleet_reader._permitted_projects"


class TestExportFleet(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        frappe.local.response = frappe._dict()
        self.plate = f"EXP {frappe.generate_hash(length=6)}"
        self.vehicle = (
            frappe.get_doc({"doctype": "Salis Vehicle", "plate_number": self.plate, "status": "Active"})
            .insert(ignore_permissions=True)
            .name
        )

    def _csv(self):
        # build_csv_response writes the file body into frappe.response["result"].
        self.assertEqual(frappe.response.get("type"), "csv")
        return frappe.response.get("result") or ""

    def test_unscoped_export_streams_csv_with_vehicle(self):
        with patch(_RESOLVER, return_value=(True, None)):
            operations_control.export_fleet()
        body = self._csv()
        self.assertIn("Plate", body)  # header row present
        self.assertIn(self.plate, body)  # the vehicle is in the file

    def test_export_respects_server_side_scope(self):
        # Scoped to a project that does not own this vehicle: the export must omit
        # it even though it exists, proving scope is enforced server-side.
        ghost = f"NO-SUCH-PROJECT-{frappe.generate_hash(length=10)}"
        with patch(_RESOLVER, return_value=(False, [ghost])):
            operations_control.export_fleet()
        body = self._csv()
        self.assertIn("Plate", body)
        self.assertNotIn(self.plate, body)
