# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today

from apex.tests.factories import default_company, make_supplier


def _telecom_contract(**overrides):
    fields = {
        "doctype": "Telecom Contract",
        "company": default_company(),
        "supplier": make_supplier("_T-Telecom Supplier"),
        "contract_start_date": today(),
        "contract_end_date": add_days(today(), 365),
        "billing_frequency": "Monthly",
        "recurring_amount": 500,
        "currency": "SAR",
    }
    fields.update(overrides)
    return frappe.get_doc(fields)


class TestTelecomContractDates(FrappeTestCase):
    def test_an_end_date_before_the_start_date_is_refused(self):
        doc = _telecom_contract(
            contract_start_date=today(), contract_end_date=add_days(today(), -1)
        )
        with self.assertRaises(frappe.ValidationError):
            doc.insert(ignore_permissions=True)


class TestTelecomContractStatusSync(FrappeTestCase):
    def test_submitting_a_contract_with_a_future_end_date_marks_it_active(self):
        doc = _telecom_contract(
            contract_end_date=add_days(today(), 30)
        ).insert(ignore_permissions=True)
        doc.submit()
        self.assertEqual(doc.status, "Active")
        self.addCleanup(doc.cancel)

    def test_submitting_a_contract_whose_end_date_has_passed_marks_it_expired(self):
        doc = _telecom_contract(
            contract_start_date=add_days(today(), -60),
            contract_end_date=add_days(today(), -1),
        ).insert(ignore_permissions=True)
        doc.submit()
        self.assertEqual(doc.status, "Expired")
        self.addCleanup(doc.cancel)

    def test_cancelling_a_submitted_contract_marks_it_terminated(self):
        doc = _telecom_contract(
            contract_end_date=add_days(today(), 30)
        ).insert(ignore_permissions=True)
        doc.submit()
        doc.cancel()
        self.assertEqual(doc.status, "Terminated")
