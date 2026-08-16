# Copyright (c) 2026, afmcoltd
"""Form dashboards: the Employee and Supplier overrides MERGE into the native dashboard rather
than replacing it, and the Building metrics reader returns its shape.

The two merge cases never needed a database at all — they hand the override a native payload and
read the result. Only the metrics case needs a building, and that one comes from
``test_records.json`` rather than a Company, a Cost Center lookup, a Site and a Building built
inside the test to read five dictionary keys back.
"""

from __future__ import annotations

from frappe.tests.utils import FrappeTestCase

from apex.habitat.api import employee_links, supplier_links
from apex.habitat.api.building_dashboard import get_building_metrics

test_dependencies = ["Building"]

BUILDING = "_Test Building"


class TestFormDashboards(FrappeTestCase):
    def test_the_employee_override_keeps_the_native_transactions(self):
        native = {
            "fieldname": "employee",
            "transactions": [{"label": "Native HR", "items": ["Salary Slip"]}],
            "non_standard_fieldnames": {"Salary Slip": "employee"},
        }
        out = employee_links.get_data(data=native)

        labels = [t["label"] for t in out["transactions"]]
        self.assertIn("Native HR", labels, "native transactions must be preserved (merge, not replace)")
        self.assertIn("Custody", labels)
        self.assertEqual(out["non_standard_fieldnames"]["Custody Issue"], "issued_to_employee")
        self.assertIsInstance(employee_links.get_data(data=None), dict)

    def test_the_supplier_override_keeps_the_native_transactions(self):
        native = {
            "fieldname": "supplier",
            "transactions": [{"label": "Purchasing", "items": ["Purchase Order"]}],
            "non_standard_fieldnames": {},
        }
        out = supplier_links.get_data(data=native)

        labels = [t["label"] for t in out["transactions"]]
        self.assertIn("Purchasing", labels, "native ERPNext supplier links must be preserved")
        self.assertIn("Cost Recovery", labels)
        self.assertEqual(out["non_standard_fieldnames"]["Accommodation Ledger"], "billed_to_supplier")

    def test_the_building_metrics_reader_returns_its_shape(self):
        metrics = get_building_metrics(BUILDING)

        for key in ("labels", "occupancy", "active_occupants", "open_maintenance", "open_custody"):
            self.assertIn(key, metrics)
        self.assertEqual(metrics["active_occupants"], 0)
        self.assertIsInstance(metrics["labels"], list)
