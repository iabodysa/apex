# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today


def _freelancer(**overrides):
    fields = {
        "doctype": "Freelancer",
        "full_name": "_T-Freelancer Validate",
        "national_id_or_iqama": frappe.generate_hash(length=10),
        "contract_start_date": today(),
        "contract_end_date": add_days(today(), 365),
        "monthly_salary": 4000,
    }
    fields.update(overrides)
    return frappe.get_doc(fields)


class TestFreelancerContractWindow(FrappeTestCase):
    def test_a_contract_ending_on_its_start_date_is_refused(self):
        doc = _freelancer(contract_end_date=today())
        with self.assertRaises(frappe.ValidationError):
            doc.insert(ignore_permissions=True)

    def test_a_contract_ending_after_its_start_is_accepted(self):
        doc = _freelancer().insert(ignore_permissions=True)
        self.assertEqual(doc.doctype, "Freelancer")


class TestFreelancerSalary(FrappeTestCase):
    def test_a_zero_monthly_salary_is_refused(self):
        doc = _freelancer(monthly_salary=0)
        with self.assertRaises(frappe.ValidationError):
            doc.insert(ignore_permissions=True)


class TestFreelancerStatusDerivation(FrappeTestCase):
    def test_a_contract_whose_end_date_has_passed_is_marked_expired_on_save(self):
        doc = _freelancer(
            contract_start_date=add_days(today(), -60),
            contract_end_date=add_days(today(), -1),
        ).insert(ignore_permissions=True)
        self.assertEqual(doc.status, "Expired")

    def test_a_terminated_freelancer_stays_terminated_past_its_end_date(self):
        doc = _freelancer(
            contract_start_date=add_days(today(), -60),
            contract_end_date=add_days(today(), -1),
            status="Terminated",
        ).insert(ignore_permissions=True)
        self.assertEqual(doc.status, "Terminated")
