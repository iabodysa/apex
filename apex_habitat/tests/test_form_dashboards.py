# Copyright (c) 2026, AFMCO and contributors
"""Form dashboards: the Employee/Supplier overrides MERGE into the native
dashboard (don't replace it), and the Building metrics reader returns its shape."""

import frappe
from apex_habitat.tests.test_utils import ApexHabitatTestCase
from apex_habitat.habitat.api import employee_links, supplier_links
from apex_habitat.habitat.api.building_dashboard import get_building_metrics


def _h(n=4):
    return frappe.generate_hash(length=n).upper()


class TestFormDashboards(ApexHabitatTestCase):
    def test_employee_override_merges_native(self):
        native = {"fieldname": "employee",
                  "transactions": [{"label": "Native HR", "items": ["Salary Slip"]}],
                  "non_standard_fieldnames": {"Salary Slip": "employee"}}
        out = employee_links.get_data(data=native)
        labels = [t["label"] for t in out["transactions"]]
        self.assertIn("Native HR", labels, "native transactions must be preserved (merge, not replace)")
        self.assertIn("Custody", labels)
        self.assertEqual(out["non_standard_fieldnames"]["Custody Issue"], "issued_to_employee")
        # the old no-arg signature would TypeError here:
        self.assertIsInstance(employee_links.get_data(data=None), dict)

    def test_supplier_override_merges_native(self):
        native = {"fieldname": "supplier",
                  "transactions": [{"label": "Purchasing", "items": ["Purchase Order"]}],
                  "non_standard_fieldnames": {}}
        out = supplier_links.get_data(data=native)
        labels = [t["label"] for t in out["transactions"]]
        self.assertIn("Purchasing", labels, "native ERPNext supplier links must be preserved")
        self.assertIn("Cost Recovery", labels)
        self.assertEqual(out["non_standard_fieldnames"]["Accommodation Ledger"], "billed_to_supplier")

    def test_building_metrics_shape(self):
        company = frappe.db.get_value("Company", {}) or frappe.get_doc({
            "doctype": "Company", "company_name": "Test Co", "default_currency": "SAR",
            "country": "Saudi Arabia"}).insert(ignore_permissions=True).name
        cc = frappe.db.get_value("Cost Center", {"is_group": 0, "company": company}) or frappe.db.get_value("Cost Center", {"is_group": 0})
        site = frappe.get_doc({"doctype": "Accommodation Site", "site_name": _h(6)}).insert(ignore_permissions=True)
        b = frappe.get_doc({"doctype": "Accommodation Building", "building_name": "B " + _h(),
                            "site": site.name, "total_capacity": 4, "default_cost_center": cc}).insert(ignore_permissions=True)
        m = get_building_metrics(b.name)
        for key in ("labels", "occupancy", "active_occupants", "open_maintenance", "open_custody"):
            self.assertIn(key, m)
        self.assertEqual(m["active_occupants"], 0)
        self.assertIsInstance(m["labels"], list)
