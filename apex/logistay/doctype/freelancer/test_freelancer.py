# Copyright (c) 2026, AFMCO and contributors
"""Tests for the Freelancer master: validation, the ID unique guard, the
permlevel-1 PII gate, and the accounting-party proof (Journal/Payment Entry)."""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, nowdate

from apex.tests import factories


class TestFreelancer(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")

    def _doc(self, **overrides):
        data = {
            "doctype": "Freelancer",
            "full_name": "Test Freelancer",
            "national_id_or_iqama": f"ID{frappe.generate_hash(length=12)}",
            "contract_start_date": nowdate(),
            "contract_end_date": add_days(nowdate(), 180),
            "monthly_salary": 3000,
        }
        data.update(overrides)
        return frappe.get_doc(data)

    def test_saves_with_required_fields(self):
        doc = self._doc().insert(ignore_permissions=True)
        self.assertTrue(doc.name.startswith("FRL-"))
        self.assertEqual(doc.status, "Active")

    def test_rejects_end_before_or_equal_start(self):
        with self.assertRaises(frappe.ValidationError):
            self._doc(contract_end_date=add_days(nowdate(), -1)).insert(
                ignore_permissions=True
            )

    def test_rejects_non_positive_salary(self):
        with self.assertRaises(frappe.ValidationError):
            self._doc(monthly_salary=0).insert(ignore_permissions=True)

    def test_status_derives_expired_for_past_contract(self):
        # [#9od32f]
        doc = self._doc(
            contract_start_date=add_days(nowdate(), -200),
            contract_end_date=add_days(nowdate(), -10),
        ).insert(ignore_permissions=True)
        self.assertEqual(doc.status, "Expired")

    def test_rejects_duplicate_national_id(self):
        nid = f"ID{frappe.generate_hash(length=12)}"
        self._doc(national_id_or_iqama=nid).insert(ignore_permissions=True)
        with self.assertRaises(Exception):
            # [#24o1sz]
            self._doc(national_id_or_iqama=nid).insert(ignore_permissions=True)

    def test_permlevel_pii_hidden_from_unprivileged_role(self):
        """A role with permlevel-0 read but no permlevel-1 read cannot see the PII.
        Internal Auditor reads at permlevel 0 only — the API strips national_id /
        mobile from its view."""
        doc = self._doc(mobile_number="0500000000").insert(ignore_permissions=True)

        user_id = f"freelance_auditor_{frappe.generate_hash(length=12)}@example.com"
        user = frappe.get_doc(
            {
                "doctype": "User",
                "email": user_id,
                "first_name": "Auditor",
                "roles": [{"role": "Internal Auditor"}],
            }
        ).insert(ignore_permissions=True)

        frappe.set_user(user.name)
        try:
            fetched = frappe.get_doc("Freelancer", doc.name)
            fetched.check_permission("read")
            # [#b4mp7e]
            fetched.apply_fieldlevel_read_permissions()
            stripped = fetched.as_dict()
            self.assertIsNone(stripped.get("national_id_or_iqama"))
            self.assertIsNone(stripped.get("mobile_number"))
            # [#6wqlmz]
            self.assertEqual(stripped.get("full_name"), "Test Freelancer")
        finally:
            frappe.set_user("Administrator")

    def test_freelance_is_an_accounting_party(self):
        """The core proof: with the custom Party Type registered, a Journal Entry
        can carry party_type='Freelancer' + party=<a freelance>.

        [#a140as] The registration used to be a class-level ``skipUnless``, evaluated
        at IMPORT time — so the one test that proves the shipped ``party_type.json``
        fixture actually landed was silently dropped whenever it had not. Assert it:
        the Party Type is shipped by this app and erpnext is a required app, so a
        missing one is a fixture regression, not a portability concern.
        """
        self.assertTrue(
            frappe.db.exists("DocType", "Journal Entry"),
            "ERPNext Journal Entry must be installed — erpnext is a required app",
        )
        self.assertTrue(
            frappe.db.exists("Party Type", "Freelancer"),
            "the Freelancer Party Type must be registered — see apex/fixtures/party_type.json",
        )

        freelance = self._doc().insert(ignore_permissions=True)

        # [#a140fx] Built, not skipped on: a fresh CI site's chart is not guaranteed
        # to carry a non-group Payable and Cash account in the company's base
        # currency, and without both there is no Journal Entry to hang the party on.
        company = factories.ensure_company()
        # [#jbf66z]
        base_currency = frappe.db.get_value("Company", company, "default_currency")
        payable = factories.ensure_account(company, "Payable", "Liability", base_currency)
        cash = factories.ensure_account(company, "Cash", "Asset", base_currency)

        je = frappe.get_doc(
            {
                "doctype": "Journal Entry",
                "voucher_type": "Journal Entry",
                "company": company,
                "posting_date": nowdate(),
                "accounts": [
                    {
                        "account": payable,
                        "party_type": "Freelancer",
                        "party": freelance.name,
                        "credit_in_account_currency": 3000,
                    },
                    {"account": cash, "debit_in_account_currency": 3000},
                ],
            }
        )
        # [#lmolqb]
        je.set_missing_values()
        je.validate()
        self.assertEqual(je.accounts[0].party_type, "Freelancer")
        self.assertEqual(je.accounts[0].party, freelance.name)
