import frappe
from frappe.tests.utils import FrappeTestCase

# Prevent Frappe test runner from recursively resolving Link-field dependencies
# on external DocTypes that require ERPNext (not installed in CI bench).
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
        # 0 passes the reqd check (it is a value, not empty) but is logically invalid —
        # the controller must reject it so assets can't "never depreciate" (bug #8).
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
