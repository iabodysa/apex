# Copyright (c) 2026, AFMCO and contributors
"""The six SIM Operations reports derive from operational records and return
well-formed (columns, rows); the assigned-suspended digest runs cleanly."""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.logistay.report.current_sim_custody import current_sim_custody
from apex.logistay.report.employees_holding_multiple_sims import (
    employees_holding_multiple_sims,
)
from apex.logistay.report.sim_exceptions import sim_exceptions
from apex.logistay.report.sims_by_contract_and_supplier import (
    sims_by_contract_and_supplier,
)
from apex.logistay.report.telecom_contract_expiry import telecom_contract_expiry
from apex.logistay.report.telecom_cost_allocation import telecom_cost_allocation
from apex.logistay.tasks import sim_alerts
from apex.tests import factories

ALL_REPORTS = [
    current_sim_custody,
    employees_holding_multiple_sims,
    sims_by_contract_and_supplier,
    telecom_contract_expiry,
    telecom_cost_allocation,
    sim_exceptions,
]


class TestSIMReports(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = factories.make_company("Test AFMCO").name
        cls.employee = factories.make_employee("Report Holder", company=cls.company).name
        cls.contract = frappe.get_doc(
            {
                "doctype": "Telecom Contract",
                "naming_series": "TEL-CTR-.YYYY.-.#####",
                "company": cls.company,
                "supplier": "QA-TELECOM-SUPPLIER",
                "contract_start_date": "2026-01-01",
                "contract_end_date": frappe.utils.add_days(frappe.utils.today(), 20),
                "billing_frequency": "Monthly",
                "recurring_amount": 100,
                "currency": "SAR",
            }
        )
        cls.contract.insert(ignore_permissions=True, ignore_links=True)
        cls.contract.submit()
        cls.sim = frappe.get_doc(
            {
                "doctype": "SIM Card",
                "naming_series": "SIM-.YYYY.-.#####",
                "company": cls.company,
                "telecom_contract": cls.contract.name,
                "mobile_number": "0553330001",
            }
        ).insert(ignore_permissions=True, ignore_links=True)
        frappe.get_doc(
            {
                "doctype": "SIM Custody Assignment",
                "naming_series": "SIM-CUST-.YYYY.-.#####",
                "company": cls.company,
                "sim_card": cls.sim.name,
                "action": "Assign",
                "assignment_date": frappe.utils.today(),
                "custodian_type": "Employee",
                "employee": cls.employee,
            }
        ).insert(ignore_permissions=True, ignore_links=True).submit()

    def test_all_reports_return_columns_and_rows(self):
        for module in ALL_REPORTS:
            columns, data = module.execute({"company": self.company})
            self.assertTrue(columns, f"{module.__name__} returned no columns")
            self.assertIsInstance(data, list)

    def test_current_custody_lists_the_assigned_sim(self):
        _columns, data = current_sim_custody.execute({"company": self.company})
        mobiles = {row["mobile_number"] for row in data}
        self.assertIn("0553330001", mobiles)

    def test_expiry_report_flags_soon(self):
        _columns, data = telecom_contract_expiry.execute({"company": self.company, "within_days": 30})
        names = {row["name"] for row in data}
        self.assertIn(self.contract.name, names)

    def test_assigned_suspended_digest_runs(self):
        # No suspended/lost assigned SIMs -> no-op, must not raise.
        sim_alerts.assigned_suspended_or_lost_watch()
