# Copyright (c) 2026, AFMCO and contributors
import frappe
from frappe.tests.utils import FrappeTestCase

from apex.tests import factories

test_ignore = [
    "Company",
    "Supplier",
    "Currency",
    "Cost Center",
    "Project",
    "Item",
    "Employee",
    "Department",
]


class TestSIMCustodyAssignment(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = factories.make_company("Test AFMCO").name
        cls.cost_center = frappe.db.get_value("Company", cls.company, "cost_center")
        cls.employee = factories.make_employee("Custody Holder One", company=cls.company).name
        if cls.cost_center:
            frappe.db.set_value("Employee", cls.employee, "payroll_cost_center", cls.cost_center)
        cls.contract = frappe.get_doc(
            {
                "doctype": "Telecom Contract",
                "naming_series": "TEL-CTR-.YYYY.-.#####",
                "company": cls.company,
                "supplier": "QA-TELECOM-SUPPLIER",
                "contract_start_date": "2026-01-01",
                "contract_end_date": "2026-12-31",
                "billing_frequency": "Monthly",
                "recurring_amount": 100,
                "currency": "SAR",
            }
        )
        cls.contract.insert(ignore_permissions=True, ignore_links=True)

    def tearDown(self):
        frappe.db.rollback()

    def _sim(self, mobile="0551000001"):
        return frappe.get_doc(
            {
                "doctype": "SIM Card",
                "naming_series": "SIM-.YYYY.-.#####",
                "company": self.company,
                "telecom_contract": self.contract.name,
                "mobile_number": mobile,
            }
        ).insert(ignore_permissions=True, ignore_links=True)

    def _event(self, sim, action, **kw):
        doc = frappe.get_doc(
            {
                "doctype": "SIM Custody Assignment",
                "naming_series": "SIM-CUST-.YYYY.-.#####",
                "company": self.company,
                "sim_card": sim.name,
                "action": action,
                "assignment_date": kw.pop("assignment_date", "2026-06-01"),
                **kw,
            }
        )
        doc.insert(ignore_permissions=True, ignore_links=True)
        doc.submit()
        return doc

    def _status(self, sim):
        return frappe.db.get_value("SIM Card", sim.name, "status")

    def test_assign_projects_state_and_snapshots_cost_center(self):
        sim = self._sim()
        event = self._event(sim, "Assign", custodian_type="Employee", employee=self.employee)
        self.assertEqual(self._status(sim), "Assigned")
        projection = frappe.db.get_value(
            "SIM Card",
            sim.name,
            ["current_custodian_employee", "current_assignment", "current_cost_center"],
            as_dict=True,
        )
        self.assertEqual(projection.current_custodian_employee, self.employee)
        self.assertEqual(projection.current_assignment, event.name)
        # Cost center resolved from the employee and frozen on the event.
        self.assertEqual(event.cost_center, self.cost_center)
        self.assertEqual(projection.current_cost_center, self.cost_center)

    def test_only_one_active_custody(self):
        sim = self._sim()
        self._event(sim, "Assign", custodian_type="Employee", employee=self.employee)
        with self.assertRaises(frappe.ValidationError):
            self._event(sim, "Assign", custodian_type="Employee", employee=self.employee)

    def test_suspended_sim_cannot_be_assigned(self):
        sim = self._sim()
        self._event(sim, "Suspend")
        self.assertEqual(self._status(sim), "Suspended")
        with self.assertRaises(frappe.ValidationError):
            self._event(sim, "Assign", custodian_type="Employee", employee=self.employee)

    def test_transfer_return_reactivate_cycle(self):
        sim = self._sim()
        self._event(sim, "Assign", custodian_type="Employee", employee=self.employee)
        project = factories.make_project("SIM Custody Project")
        self._event(sim, "Transfer", custodian_type="Project", project=project)
        self.assertEqual(self._status(sim), "Assigned")
        self.assertEqual(
            frappe.db.get_value("SIM Card", sim.name, "current_project"), project
        )
        self._event(sim, "Return")
        self.assertEqual(self._status(sim), "Available")
        self.assertIsNone(frappe.db.get_value("SIM Card", sim.name, "current_custodian_employee"))
        # Suspend an Available SIM, then Reactivate back to Available.
        self._event(sim, "Suspend")
        self._event(sim, "Reactivate")
        self.assertEqual(self._status(sim), "Available")

    def test_incompatible_company_fails_closed(self):
        sim = self._sim()
        other_company = factories.make_company("Other AFMCO", abbr="OAFM").name
        other_employee = factories.make_employee("Foreign Holder", company=other_company).name
        with self.assertRaises(frappe.ValidationError):
            self._event(sim, "Assign", custodian_type="Employee", employee=other_employee)

    def test_projection_matches_latest_after_cancel(self):
        sim = self._sim()
        first = self._event(sim, "Assign", custodian_type="Employee", employee=self.employee)
        self._event(sim, "Return")
        self.assertEqual(self._status(sim), "Available")
        # Cancelling the Return rolls the SIM back to the Assigned state it had.
        returns = frappe.get_all(
            "SIM Custody Assignment",
            filters={"sim_card": sim.name, "action": "Return", "docstatus": 1},
            pluck="name",
        )
        frappe.get_doc("SIM Custody Assignment", returns[0]).cancel()
        self.assertEqual(self._status(sim), "Assigned")
        self.assertEqual(
            frappe.db.get_value("SIM Card", sim.name, "current_assignment"), first.name
        )
