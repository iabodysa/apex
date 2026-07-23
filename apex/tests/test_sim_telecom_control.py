# Copyright (c) 2026, AFMCO and contributors
"""Telecom Control read API: correct, bounded, permission-scoped metrics with no
unrelated employee data leaking into rows or the detail drawer."""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.sim_operations.api import telecom_control
from apex.tests import factories


class TestTelecomControlApi(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = factories.make_company("Test AFMCO").name
        cls.employee = factories.make_employee("Control Holder", company=cls.company).name
        cls.contract = frappe.get_doc(
            {
                "doctype": "Telecom Contract",
                "naming_series": "TEL-CTR-.YYYY.-.#####",
                "company": cls.company,
                "supplier": "QA-TELECOM-SUPPLIER",
                "contract_start_date": "2026-01-01",
                "contract_end_date": frappe.utils.add_days(frappe.utils.today(), 15),
                "billing_frequency": "Monthly",
                "recurring_amount": 100,
                "currency": "SAR",
            }
        )
        cls.contract.insert(ignore_permissions=True, ignore_links=True)
        cls.contract.submit()
        cls.sims = [cls._sim(f"05590000{i:02d}") for i in range(3)]
        # Assign one SIM to the employee.
        frappe.get_doc(
            {
                "doctype": "SIM Custody Assignment",
                "naming_series": "SIM-CUST-.YYYY.-.#####",
                "company": cls.company,
                "sim_card": cls.sims[0].name,
                "action": "Assign",
                "assignment_date": frappe.utils.today(),
                "custodian_type": "Employee",
                "employee": cls.employee,
            }
        ).insert(ignore_permissions=True, ignore_links=True).submit()

    @classmethod
    def _sim(cls, mobile):
        return frappe.get_doc(
            {
                "doctype": "SIM Card",
                "naming_series": "SIM-.YYYY.-.#####",
                "company": cls.company,
                "telecom_contract": cls.contract.name,
                "mobile_number": mobile,
            }
        ).insert(ignore_permissions=True, ignore_links=True)

    def test_summary_cards(self):
        cards = telecom_control.get_summary_cards()
        self.assertGreaterEqual(cards["total_sims"], 3)
        self.assertGreaterEqual(cards["assigned"], 1)
        self.assertGreaterEqual(cards["active_contracts"], 1)
        self.assertGreaterEqual(cards["expiring_soon"], 1)

    def test_charts_have_status_buckets(self):
        charts = telecom_control.get_charts()
        labels = {row["label"] for row in charts["by_status"]}
        self.assertIn("Assigned", labels)

    def test_rows_paging_is_bounded(self):
        result = telecom_control.get_sim_rows(page_size=99999)
        self.assertLessEqual(result["page_size"], telecom_control.MAX_PAGE_SIZE)
        self.assertGreaterEqual(result["total"], 3)

    def test_rows_filter_by_status(self):
        result = telecom_control.get_sim_rows(filters={"status": "Assigned"})
        self.assertTrue(all(r["status"] == "Assigned" for r in result["rows"]))

    def test_invalid_filter_key_ignored(self):
        # An unknown/injection filter key is dropped, not applied or errored.
        result = telecom_control.get_sim_rows(filters={"date_of_birth": "1990-01-01"})
        self.assertGreaterEqual(result["total"], 3)

    def test_contract_expiry_lists_soon(self):
        result = telecom_control.get_contract_expiry(within_days=30)
        names = {r["name"] for r in result["rows"]}
        self.assertIn(self.contract.name, names)

    def test_detail_drawer_has_history_no_unrelated_employee_fields(self):
        detail = telecom_control.get_sim_detail(self.sims[0].name)
        self.assertEqual(detail["name"], self.sims[0].name)
        self.assertTrue(detail["history"])
        self.assertEqual(detail.get("custodian_name"), "Control Holder")
        # Only the display name is exposed; no other employee fields.
        for leaked in ("date_of_birth", "gender", "date_of_joining", "salary"):
            self.assertNotIn(leaked, detail)

    def test_cost_center_totals_bounded(self):
        result = telecom_control.get_cost_center_totals()
        self.assertLessEqual(len(result["rows"]), telecom_control.TOP_N)
