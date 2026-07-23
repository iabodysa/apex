# Copyright (c) 2026, AFMCO and contributors
import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

# [#8evoal]
test_ignore = [
    "Additional Salary",
    "Asset",
    "Asset Movement",
    "Company",
    "Cost Center",
    "Currency",
    "Employee",
    "Item",
    "Payment Entry",
    "Project",
    "Purchase Invoice",
    "Role",
    "Salary Component",
    "Supplier",
    "User",
]


class TestOperationalDepreciationPolicy(FrappeTestCase):

    def test_create_valid_policy(self):
        doc = frappe.get_doc({
            "doctype": "Operational Depreciation Policy",
            "policy_name": "QA Straight Line Policy",
            "useful_life_years": 5,
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.assertEqual(doc.useful_life_years, 5)
        frappe.delete_doc("Operational Depreciation Policy", doc.name, force=True, ignore_permissions=True)

    def test_missing_policy_name_raises(self):
        doc = frappe.get_doc({
            "doctype": "Operational Depreciation Policy",
            "useful_life_years": 5,
        })
        with self.assertRaises(frappe.exceptions.ValidationError):
            doc.insert(ignore_permissions=True, ignore_links=True)

    def test_missing_useful_life_raises(self):
        doc = frappe.get_doc({
            "doctype": "Operational Depreciation Policy",
            "policy_name": "QA Policy No Life",
        })
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert(ignore_permissions=True, ignore_links=True)

    def test_zero_useful_life_raises(self):
        # [#roxncg]
        doc = frappe.get_doc({
            "doctype": "Operational Depreciation Policy",
            "policy_name": "QA Zero Life",
            "useful_life_years": 0,
        })
        with self.assertRaises(frappe.exceptions.ValidationError):
            doc.insert(ignore_permissions=True, ignore_links=True)

    def test_negative_useful_life_raises(self):
        doc = frappe.get_doc({
            "doctype": "Operational Depreciation Policy",
            "policy_name": "QA Negative Life",
            "useful_life_years": -3,
        })
        with self.assertRaises(frappe.exceptions.ValidationError):
            doc.insert(ignore_permissions=True, ignore_links=True)

    def test_residual_value_above_100_raises(self):
        # [#3n2vbz]
        doc = frappe.get_doc({
            "doctype": "Operational Depreciation Policy",
            "policy_name": "QA Residual Over",
            "useful_life_years": 5,
            "residual_value_pct": 150,
        })
        with self.assertRaises(frappe.exceptions.ValidationError):
            doc.insert(ignore_permissions=True, ignore_links=True)

    def test_residual_value_negative_raises(self):
        doc = frappe.get_doc({
            "doctype": "Operational Depreciation Policy",
            "policy_name": "QA Residual Negative",
            "useful_life_years": 5,
            "residual_value_pct": -1,
        })
        with self.assertRaises(frappe.exceptions.ValidationError):
            doc.insert(ignore_permissions=True, ignore_links=True)

    def test_residual_value_bounds_inclusive(self):
        # [#dgwmjf]
        for pct in (0, 100):
            doc = frappe.get_doc({
                "doctype": "Operational Depreciation Policy",
                "policy_name": f"QA Residual {pct}",
                "useful_life_years": 5,
                "residual_value_pct": pct,
            })
            doc.insert(ignore_permissions=True, ignore_links=True)
            self.assertEqual(flt(doc.residual_value_pct), pct)
            frappe.delete_doc(
                "Operational Depreciation Policy", doc.name, force=True, ignore_permissions=True
            )
