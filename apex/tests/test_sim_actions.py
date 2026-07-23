# Copyright (c) 2026, AFMCO and contributors
"""Telecom Control page actions: succeed from valid states, fail from invalid or
wrong-company states; a mobile edit updates the SIM in place with no separate
history DocType."""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.sim_operations.api import sim_actions
from apex.tests import factories


class TestSIMActions(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = factories.make_company("Test AFMCO").name
        cls.employee = factories.make_employee("Action Holder", company=cls.company).name
        cls.contract = cls._contract(cls.company, "QA-TELECOM-SUPPLIER")

    @classmethod
    def _contract(cls, company, supplier):
        factories.make_supplier(supplier)
        doc = frappe.get_doc(
            {
                "doctype": "Telecom Contract",
                "naming_series": "TEL-CTR-.YYYY.-.#####",
                "company": company,
                "supplier": supplier,
                "contract_start_date": "2026-01-01",
                "contract_end_date": "2026-12-31",
                "billing_frequency": "Monthly",
                "recurring_amount": 100,
                "currency": "SAR",
            }
        )
        doc.insert(ignore_permissions=True, ignore_links=True)
        doc.submit()
        return doc

    def _sim(self, mobile="0557000001"):
        return frappe.get_doc(
            {
                "doctype": "SIM Card",
                "naming_series": "SIM-.YYYY.-.#####",
                "company": self.company,
                "telecom_contract": self.contract.name,
                "mobile_number": mobile,
            }
        ).insert(ignore_permissions=True, ignore_links=True)

    def setUp(self):
        # Per-test savepoint so a test's rollback undoes only its own writes and
        # never the class fixtures (company/employee/contract) from setUpClass — a
        # bare frappe.db.rollback() wipes those on the first test, which is why the
        # later tests could not find the Employee/Supplier they referenced.
        frappe.db.savepoint("sim_actions_test")

    def tearDown(self):
        frappe.db.rollback(save_point="sim_actions_test")

    def test_assign_from_available_succeeds(self):
        sim = self._sim()
        result = sim_actions.perform_custody_action(
            sim.name, "Assign", custodian_type="Employee", employee=self.employee
        )
        self.assertEqual(result["status"], "Assigned")

    def test_assign_from_assigned_fails(self):
        sim = self._sim()
        sim_actions.perform_custody_action(sim.name, "Assign", custodian_type="Employee", employee=self.employee)
        with self.assertRaises(frappe.ValidationError):
            sim_actions.perform_custody_action(sim.name, "Assign", custodian_type="Employee", employee=self.employee)

    def test_unknown_action_rejected(self):
        sim = self._sim()
        with self.assertRaises(frappe.ValidationError):
            sim_actions.perform_custody_action(sim.name, "Explode")

    def test_edit_mobile_in_place_no_history_doctype(self):
        sim = self._sim("0557000002")
        before = frappe.db.count("SIM Custody Assignment", {"sim_card": sim.name})
        sim_actions.edit_mobile_number(sim.name, "0557000099")
        self.assertEqual(frappe.db.get_value("SIM Card", sim.name, "mobile_number"), "0557000099")
        # No custody record and no bespoke history DocType was spawned by the edit.
        self.assertEqual(frappe.db.count("SIM Custody Assignment", {"sim_card": sim.name}), before)
        self.assertFalse(frappe.db.exists("DocType", "SIM Mobile Number History"))

    def test_move_to_same_company_contract_succeeds(self):
        sim = self._sim("0557000003")
        other_contract = self._contract(self.company, "QA-TELECOM-SUPPLIER-2")
        result = sim_actions.move_to_contract(sim.name, other_contract.name)
        self.assertEqual(result["telecom_contract"], other_contract.name)

    def test_move_to_other_company_contract_fails_closed(self):
        sim = self._sim("0557000004")
        other_company = factories.make_company("Other AFMCO", abbr="OAFM").name
        foreign_contract = self._contract(other_company, "QA-TELECOM-SUPPLIER-3")
        with self.assertRaises(frappe.ValidationError):
            sim_actions.move_to_contract(sim.name, foreign_contract.name)
