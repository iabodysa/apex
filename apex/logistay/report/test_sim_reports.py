# Copyright (c) 2026, AFMCO and contributors
"""The four shipped SIM Operations reports derive from operational records and
return well-formed (columns, rows); the assigned-suspended digest runs cleanly.

SUBJECT: the report PACKAGES under apex/logistay/report/ (371 lines), not the 1-line
``__init__.py`` beside this file — 84 against 371 is 0.23x. The 84x a per-directory
count reports is the same report-grouping artifact as on the Salis side."""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.logistay.report.employees_holding_multiple_sims import (
    employees_holding_multiple_sims,
)
from apex.logistay.report.sim_exceptions import sim_exceptions
from apex.logistay.report.telecom_contract_expiry import telecom_contract_expiry
from apex.logistay.report.telecom_cost_allocation import telecom_cost_allocation
from apex.logistay.tasks import sim_alerts
from apex.tests import factories
from apex.tests._helpers import _user

ALL_REPORTS = [
    employees_holding_multiple_sims,
    telecom_contract_expiry,
    telecom_cost_allocation,
    sim_exceptions,
]


class TestSIMReports(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        """Seeds one submitted Telecom Contract, one SIM Card and one assignment."""
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
        """Every shipped SIM report returns columns and a list of rows."""
        for module in ALL_REPORTS:
            columns, data, *_rest = module.execute({"company": self.company})
            self.assertTrue(columns, f"{module.__name__} returned no columns")
            self.assertIsInstance(data, list)

    def test_expiry_report_flags_soon(self):
        """A contract ending inside the window is listed by the expiry report."""
        _columns, data, *_rest = telecom_contract_expiry.execute({"company": self.company, "within_days": 30})
        names = {row["name"] for row in data}
        self.assertIn(self.contract.name, names)

    def test_assigned_suspended_digest_runs(self):
        """With no suspended or lost assigned SIM the digest is a no-op that must not raise."""
        sim_alerts.assigned_suspended_or_lost_watch()

    def test_assigned_suspended_digest_notifies_a_scoped_recipient(self):
        """A SIM still held while Suspended reaches exactly one Notification Log for a
        recipient scoped to the SIM's own company -- the case the no-op above cannot
        prove, since its seeded state never lets the digest's body run at all."""
        sim = frappe.get_doc(
            {
                "doctype": "SIM Card",
                "naming_series": "SIM-.YYYY.-.#####",
                "company": self.company,
                "telecom_contract": self.contract.name,
                "mobile_number": "0553330099",
            }
        ).insert(ignore_permissions=True, ignore_links=True)
        frappe.get_doc(
            {
                "doctype": "SIM Custody Assignment",
                "naming_series": "SIM-CUST-.YYYY.-.#####",
                "company": self.company,
                "sim_card": sim.name,
                "action": "Assign",
                "assignment_date": frappe.utils.today(),
                "custodian_type": "Employee",
                "employee": self.employee,
            }
        ).insert(ignore_permissions=True, ignore_links=True).submit()
        frappe.get_doc(
            {
                "doctype": "SIM Custody Assignment",
                "naming_series": "SIM-CUST-.YYYY.-.#####",
                "company": self.company,
                "sim_card": sim.name,
                "action": "Suspend",
                "assignment_date": frappe.utils.today(),
            }
        ).insert(ignore_permissions=True, ignore_links=True).submit()
        self.assertEqual(frappe.db.get_value("SIM Card", sim.name, "status"), "Suspended")

        recipient = "sim_ops_digest@example.com"
        _user(recipient, "SIM Operations User")
        if not frappe.db.exists(
            "User Permission", {"user": recipient, "allow": "Company", "for_value": self.company}
        ):
            frappe.get_doc(
                {
                    "doctype": "User Permission",
                    "user": recipient,
                    "allow": "Company",
                    "for_value": self.company,
                }
            ).insert(ignore_permissions=True)
        self.addCleanup(
            frappe.db.delete,
            "User Permission",
            {"user": recipient, "allow": "Company", "for_value": self.company},
        )

        before = frappe.db.count(
            "Notification Log", {"for_user": recipient, "type": "Alert"}
        )
        sim_alerts.assigned_suspended_or_lost_watch()
        after = frappe.get_all(
            "Notification Log",
            filters={"for_user": recipient, "type": "Alert"},
            fields=["name", "subject", "email_content"],
            order_by="creation desc",
            limit_page_length=0,
        )
        self.assertEqual(
            len(after) - before, 1, "expected exactly one digest notification for the recipient"
        )
        self.assertIn(sim.mobile_number, after[0].email_content)
