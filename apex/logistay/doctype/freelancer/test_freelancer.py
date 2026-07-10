# Copyright (c) 2026, AFMCO and contributors
"""Tests for the Freelancer master: validation, the ID unique guard, the
permlevel-1 PII gate, and the accounting-party proof (Journal/Payment Entry)."""

from __future__ import annotations

import unittest

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, nowdate


def _accounting_available() -> bool:
    """ERPNext accounting present? Guard the Party-Entry proof so the suite runs
    on a site without erpnext installed."""
    return frappe.db.exists("DocType", "Journal Entry") and frappe.db.exists(
        "Party Type", "Freelancer"
    )


class TestFreelancer(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")

    def _doc(self, **overrides):
        data = {
            "doctype": "Freelancer",
            "full_name": "Test Freelancer",
            "national_id_or_iqama": f"ID{frappe.generate_hash(length=8)}",
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
        # A past end date flips an Active contract to Expired (Temporary Worker mirror).
        doc = self._doc(
            contract_start_date=add_days(nowdate(), -200),
            contract_end_date=add_days(nowdate(), -10),
        ).insert(ignore_permissions=True)
        self.assertEqual(doc.status, "Expired")

    def test_rejects_duplicate_national_id(self):
        nid = f"ID{frappe.generate_hash(length=8)}"
        self._doc(national_id_or_iqama=nid).insert(ignore_permissions=True)
        with self.assertRaises(Exception):
            # DB unique index (or set_only_once path) blocks a second row with the same ID.
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
            # The permlevel-1 read gate is enforced by apply_fieldlevel_read_permissions
            # (the same call the get_doc API applies before returning a doc) — it deletes
            # the fields the user has no permlevel access to. as_dict() alone does NOT.
            fetched.apply_fieldlevel_read_permissions()
            stripped = fetched.as_dict()
            self.assertIsNone(stripped.get("national_id_or_iqama"))
            self.assertIsNone(stripped.get("mobile_number"))
            # A permlevel-0 field stays visible — proves the doc itself is readable.
            self.assertEqual(stripped.get("full_name"), "Test Freelancer")
        finally:
            frappe.set_user("Administrator")

    @unittest.skipUnless(_accounting_available(), "erpnext accounting not installed")
    def test_freelance_is_an_accounting_party(self):
        """The core proof: with the custom Party Type registered, a Journal Entry
        can carry party_type='Freelancer' + party=<a freelance>."""
        freelance = self._doc().insert(ignore_permissions=True)

        company = frappe.db.get_value("Company", {}, "name")
        if not company:
            self.skipTest("no Company configured")
        # Pick accounts in the company's base currency so the JE never trips the
        # ERPNext multi-currency guard — that path is irrelevant to the party-axis proof.
        base_currency = frappe.db.get_value("Company", company, "default_currency")

        def _account(account_type):
            return frappe.db.get_value(
                "Account",
                {
                    "company": company,
                    "account_type": account_type,
                    "is_group": 0,
                    "account_currency": base_currency,
                },
                "name",
            )

        payable = _account("Payable")
        cash = _account("Cash")
        if not (payable and cash):
            self.skipTest("no payable/cash account configured")

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
        # Reaching validate without a party-type error is the proof the party axis works.
        je.set_missing_values()
        je.validate()
        self.assertEqual(je.accounts[0].party_type, "Freelancer")
        self.assertEqual(je.accounts[0].party, freelance.name)
