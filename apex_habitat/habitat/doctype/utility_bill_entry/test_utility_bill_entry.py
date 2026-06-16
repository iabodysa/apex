import frappe
from frappe.tests.utils import FrappeTestCase

# [#hlfy1g]
# [#rf8fpd]
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


class TestUtilityBillEntry(FrappeTestCase):

    def test_create_valid_bill(self):
        doc = frappe.get_doc({
            "doctype": "Utility Bill Entry",
            "naming_series": "UTIL-BILL-.YYYY.-.#####",
            "utility_account": "UTIL-ACC-QA",
            "billing_period_from": "2026-06-01",
            "billing_period_to": "2026-06-30",
            "bill_amount_sar": 1200,
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.assertEqual(doc.bill_amount_sar, 1200)
        frappe.delete_doc("Utility Bill Entry", doc.name, force=True, ignore_permissions=True)

    def test_missing_utility_account_raises(self):
        doc = frappe.get_doc({
            "doctype": "Utility Bill Entry",
            "naming_series": "UTIL-BILL-.YYYY.-.#####",
            "billing_period_from": "2026-06-01",
            "billing_period_to": "2026-06-30",
            "bill_amount_sar": 900,
        })
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert(ignore_permissions=True, ignore_links=True)

    def test_period_to_before_from_raises(self):
        from apex_habitat.habitat.doctype.utility_bill_entry.utility_bill_entry import validate

        doc = frappe.get_doc({
            "doctype": "Utility Bill Entry",
            "utility_account": "UTIL-ACC-QA",
            "billing_period_from": "2026-06-30",
            "billing_period_to": "2026-06-01",
            "bill_amount_sar": 500,
        })
        with self.assertRaises(frappe.ValidationError):
            validate(doc)

    # [#is5nbc]
    def _bill(self, **kw):
        base = {
            "doctype": "Utility Bill Entry", "naming_series": "UTIL-BILL-.YYYY.-.#####",
            "billing_period_from": "2026-06-01", "billing_period_to": "2026-06-30",
            "bill_amount_sar": 100,
        }
        base.update(kw)
        return frappe.get_doc(base)

    def test_duplicate_same_company_building_account_period_blocked(self):
        from apex_habitat.habitat.doctype.utility_bill_entry.utility_bill_entry import validate
        m = frappe.generate_hash(length=6)
        first = self._bill(company="QA-CO-" + m, building="QA-BLD-1", utility_account="ACC-" + m)
        first.insert(ignore_permissions=True, ignore_links=True)
        dup = self._bill(company="QA-CO-" + m, building="QA-BLD-1", utility_account="ACC-" + m)
        with self.assertRaises(frappe.ValidationError):
            validate(dup)
        frappe.delete_doc("Utility Bill Entry", first.name, force=True, ignore_permissions=True)

    def test_same_account_period_different_building_or_company_allowed(self):
        from apex_habitat.habitat.doctype.utility_bill_entry.utility_bill_entry import validate
        m = frappe.generate_hash(length=6)
        first = self._bill(company="QA-CO-" + m, building="QA-BLD-1", utility_account="ACC-" + m)
        first.insert(ignore_permissions=True, ignore_links=True)
        # [#ngobji]
        validate(self._bill(company="QA-CO-" + m, building="QA-BLD-2", utility_account="ACC-" + m))
        # [#ph03g4]
        validate(self._bill(company="QA-CO-OTHER-" + m, building="QA-BLD-1", utility_account="ACC-" + m))
        frappe.delete_doc("Utility Bill Entry", first.name, force=True, ignore_permissions=True)
