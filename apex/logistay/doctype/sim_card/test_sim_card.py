# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today

from apex.tests.factories import default_company, make_supplier


def _submitted_contract(company=None, **overrides):
    fields = {
        "doctype": "Telecom Contract",
        "company": company or default_company(),
        "supplier": make_supplier("_T-SIM Card Supplier"),
        "contract_start_date": today(),
        "contract_end_date": add_days(today(), 365),
        "billing_frequency": "Monthly",
        "recurring_amount": 500,
        "currency": "SAR",
    }
    fields.update(overrides)
    doc = frappe.get_doc(fields).insert(ignore_permissions=True)
    doc.submit()
    return doc


def _sim_card(contract, **overrides):
    fields = {
        "doctype": "SIM Card",
        "company": contract.company,
        "telecom_contract": contract.name,
        "mobile_number": "0500000001",
    }
    fields.update(overrides)
    return frappe.get_doc(fields)


class TestSIMCardMobileNumber(FrappeTestCase):
    def test_a_mobile_number_with_no_digits_is_refused(self):
        contract = _submitted_contract()
        doc = _sim_card(contract, mobile_number="---")
        with self.assertRaises(frappe.ValidationError):
            doc.insert(ignore_permissions=True)


class TestSIMCardContractBinding(FrappeTestCase):
    def test_a_sim_cannot_bind_to_an_unsubmitted_contract(self):
        draft_contract = frappe.get_doc(
            {
                "doctype": "Telecom Contract",
                "company": default_company(),
                "supplier": make_supplier("_T-SIM Card Draft Supplier"),
                "contract_start_date": today(),
                "contract_end_date": add_days(today(), 365),
                "billing_frequency": "Monthly",
                "recurring_amount": 500,
                "currency": "SAR",
            }
        ).insert(ignore_permissions=True)
        doc = _sim_card(draft_contract)
        with self.assertRaises(frappe.ValidationError):
            doc.insert(ignore_permissions=True)


class TestSIMCardUniqueness(FrappeTestCase):
    def test_a_second_sim_with_the_same_mobile_number_is_refused_with_its_own_message(self):
        contract = _submitted_contract()
        _sim_card(contract, mobile_number="0511111111").insert(ignore_permissions=True)
        clash = _sim_card(contract, mobile_number="0511111111")
        with self.assertRaisesRegex(frappe.ValidationError, "is already registered on SIM"):
            clash.insert(ignore_permissions=True)

    def test_a_second_sim_with_the_same_iccid_is_refused_with_its_own_message(self):
        contract = _submitted_contract()
        _sim_card(
            contract, mobile_number="0522222222", iccid="8900000000000000001"
        ).insert(ignore_permissions=True)
        clash = _sim_card(
            contract, mobile_number="0522222223", iccid="8900000000000000001"
        )
        with self.assertRaisesRegex(frappe.ValidationError, "is already registered on SIM"):
            clash.insert(ignore_permissions=True)


class TestSIMCardContractCount(FrappeTestCase):
    def test_inserting_a_sim_increments_its_contracts_sim_count(self):
        contract = _submitted_contract()
        _sim_card(contract, mobile_number="0533333333").insert(ignore_permissions=True)
        contract.reload()
        self.assertEqual(contract.sim_count, 1)
