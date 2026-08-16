# Copyright (c) 2026, afmcoltd
"""Contract test for ``get_data`` merges Habitat's Supplier-dashboard
links into the native Supplier dashboard payload WITHOUT dropping what was
already there."""

from __future__ import annotations

from frappe.tests.utils import FrappeTestCase

from apex.habitat.api.supplier_links import get_data


class TestSupplierLinksGetData(FrappeTestCase):
    def test_merges_into_an_empty_payload(self):
        data = get_data()
        self.assertEqual(data["fieldname"], "supplier")
        labels = [t["label"] for t in data["transactions"]]
        self.assertIn("Housing (Supplier-billed)", labels)
        self.assertIn("Subcontracting", labels)
        self.assertIn("Cost Recovery", labels)
        self.assertIn("Fleet (Salis)", labels)
        self.assertEqual(
            data["non_standard_fieldnames"],
            {
                "Housing Assignment": "billed_to_supplier",
                "Accommodation Ledger": "billed_to_supplier",
                "Lease": "landlord",
            },
        )

    def test_preserves_native_transactions_and_fieldnames_already_present(self):
        native = {
            "fieldname": "supplier",
            "non_standard_fieldnames": {"Purchase Order": "supplier"},
            "transactions": [{"label": "Payments", "items": ["Payment Entry"]}],
        }
        data = get_data(native)
        labels = [t["label"] for t in data["transactions"]]
        # Native entries survive alongside the merged Habitat ones.
        self.assertIn("Payments", labels)
        self.assertIn("Housing (Supplier-billed)", labels)
        self.assertEqual(data["non_standard_fieldnames"]["Purchase Order"], "supplier")
        self.assertEqual(data["non_standard_fieldnames"]["Lease"], "landlord")

    def test_does_not_overwrite_an_already_set_fieldname(self):
        data = get_data({"fieldname": "party"})
        self.assertEqual(data["fieldname"], "party")

    def test_housing_and_subcontracting_and_cost_recovery_and_fleet_items(self):
        data = get_data()
        by_label = {t["label"]: t["items"] for t in data["transactions"]}
        self.assertEqual(by_label["Housing (Supplier-billed)"], ["Housing Assignment", "Lease"])
        self.assertEqual(
            by_label["Subcontracting"],
            ["Subcontractor Service Contract", "Subcontractor Service Order"],
        )
        self.assertEqual(by_label["Cost Recovery"], ["Accommodation Ledger"])
        self.assertEqual(by_label["Fleet (Salis)"], ["Rental Office"])
