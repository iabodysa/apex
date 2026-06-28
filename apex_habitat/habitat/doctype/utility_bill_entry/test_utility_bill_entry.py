# Copyright (c) 2026, AFMCO and contributors
import frappe
from frappe.tests.utils import FrappeTestCase

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
    "Mode of Payment",
    "Payment Entry",
    "Payment Gateway",
    "Project",
    "Salis Payment Request",
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

    # [#elxeu9]
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
        # [#hottg0]
        validate(self._bill(company="QA-CO-" + m, building="QA-BLD-2", utility_account="ACC-" + m))
        # [#s61pik]
        validate(self._bill(company="QA-CO-OTHER-" + m, building="QA-BLD-1", utility_account="ACC-" + m))
        frappe.delete_doc("Utility Bill Entry", first.name, force=True, ignore_permissions=True)

    # ---- overlapping period (not only exact equal) is flagged ----
    def test_overlapping_period_same_account_blocked(self):
        from apex_habitat.habitat.doctype.utility_bill_entry.utility_bill_entry import validate
        m = frappe.generate_hash(length=6)
        first = self._bill(
            company="QA-CO-" + m, building="QA-BLD-1", utility_account="ACC-" + m,
            billing_period_from="2026-06-01", billing_period_to="2026-06-30",
        )
        first.insert(ignore_permissions=True, ignore_links=True)
        # straddles the tail of the first period -> overlap, not an exact match
        overlapping = self._bill(
            company="QA-CO-" + m, building="QA-BLD-1", utility_account="ACC-" + m,
            billing_period_from="2026-06-15", billing_period_to="2026-07-15",
        )
        with self.assertRaises(frappe.ValidationError):
            validate(overlapping)
        # a disjoint later period for the same account is still allowed
        validate(self._bill(
            company="QA-CO-" + m, building="QA-BLD-1", utility_account="ACC-" + m,
            billing_period_from="2026-07-01", billing_period_to="2026-07-31",
        ))
        frappe.delete_doc("Utility Bill Entry", first.name, force=True, ignore_permissions=True)

    # ---- negative amounts rejected in validate, no ledger row posted ----
    def test_negative_total_amount_raises(self):
        from apex_habitat.habitat.doctype.utility_bill_entry.utility_bill_entry import validate
        m = frappe.generate_hash(length=6)
        doc = self._bill(
            company="QA-CO-" + m, building="QA-BLD-1", utility_account="ACC-" + m,
            total_bill_amount_sar=-50, bill_amount_sar=0,
        )
        with self.assertRaises(frappe.ValidationError):
            validate(doc)

    def test_negative_bill_amount_raises_and_posts_no_ledger(self):
        from apex_habitat.habitat.doctype.utility_bill_entry.utility_bill_entry import validate
        m = frappe.generate_hash(length=6)
        src = "QA-UBE-NEG-" + m
        doc = self._bill(
            company="QA-CO-" + m, building="QA-BLD-1", utility_account="ACC-" + m,
            bill_amount_sar=-100,
        )
        doc.name = src
        with self.assertRaises(frappe.ValidationError):
            validate(doc)
        self.assertFalse(frappe.db.exists(
            "Accommodation Ledger",
            {"source_doctype": "Utility Bill Entry", "source_name": src},
        ))

    # ---- a backwards meter reading is a misread, not zero usage ----
    def test_backwards_meter_reading_raises(self):
        from apex_habitat.habitat.doctype.utility_bill_entry.utility_bill_entry import validate
        m = frappe.generate_hash(length=6)
        doc = self._bill(
            company="QA-CO-" + m, building="QA-BLD-1", utility_account="ACC-" + m,
            meter_reading_previous=500, meter_reading_current=400,
        )
        with self.assertRaises(frappe.ValidationError):
            validate(doc)

    def test_forward_meter_reading_computes_consumption(self):
        from apex_habitat.habitat.doctype.utility_bill_entry.utility_bill_entry import validate
        m = frappe.generate_hash(length=6)
        doc = self._bill(
            company="QA-CO-" + m, building="QA-BLD-1", utility_account="ACC-" + m,
            meter_reading_previous=500, meter_reading_current=750,
        )
        validate(doc)  # must not raise
        self.assertEqual(doc.meter_units_consumed, 250)

    def test_equal_meter_readings_allowed_zero_usage(self):
        """current == previous is genuine zero consumption, not a misread."""
        from apex_habitat.habitat.doctype.utility_bill_entry.utility_bill_entry import validate
        m = frappe.generate_hash(length=6)
        doc = self._bill(
            company="QA-CO-" + m, building="QA-BLD-1", utility_account="ACC-" + m,
            meter_reading_previous=500, meter_reading_current=500,
        )
        validate(doc)  # must not raise
        self.assertEqual(doc.meter_units_consumed, 0)

    # ---- re-running the submit side-effect posts at most one live row ----
    def _ledger_building(self, m):
        bld = frappe.get_doc({
            "doctype": "Accommodation Building", "building_name": "QA-LEDG-BLD-" + m,
            "total_capacity": 10,
        })
        bld.insert(ignore_permissions=True, ignore_links=True)
        return bld

    def _ledger_count(self, src, reversal=None):
        flt = {"source_doctype": "Utility Bill Entry", "source_name": src}
        flt["reversal_of"] = ["is", "set"] if reversal else ["is", "not set"]
        return frappe.db.count("Accommodation Ledger", flt)

    def test_post_ledger_idempotent_on_rerun(self):
        from apex_habitat.habitat.doctype.utility_bill_entry.utility_bill_entry import _post_ledger_row
        m = frappe.generate_hash(length=6)
        bld = self._ledger_building(m)
        src = "QA-UBE-IDEM-" + m
        doc = self._bill(building=bld.name, utility_type="Electricity", bill_amount_sar=300)
        doc.name = src
        _post_ledger_row(doc)
        _post_ledger_row(doc)  # re-run must be a no-op
        self.assertEqual(self._ledger_count(src), 1)
        frappe.delete_doc("Accommodation Building", bld.name, force=True, ignore_permissions=True)

    def test_cancel_negative_reversal_still_posts(self):
        from apex_habitat.habitat.doctype.utility_bill_entry.utility_bill_entry import (
            _post_ledger_row, before_cancel,
        )
        m = frappe.generate_hash(length=6)
        bld = self._ledger_building(m)
        src = "QA-UBE-REV-" + m
        doc = self._bill(building=bld.name, utility_type="Electricity", bill_amount_sar=300)
        doc.name = src
        doc.cancellation_reason = "QA reversal test"
        _post_ledger_row(doc)
        before_cancel(doc)
        # exactly one original + one negative reversal row
        self.assertEqual(self._ledger_count(src), 1)
        self.assertEqual(self._ledger_count(src, reversal=True), 1)
        rev = frappe.db.get_value(
            "Accommodation Ledger",
            {"source_doctype": "Utility Bill Entry", "source_name": src, "reversal_of": ["is", "set"]},
            "total_site_cost",
        )
        self.assertEqual(rev, -300)
        frappe.delete_doc("Accommodation Building", bld.name, force=True, ignore_permissions=True)
