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
        doc = self._doc(
            contract_start_date=add_days(nowdate(), -200),
            contract_end_date=add_days(nowdate(), -10),
        ).insert(ignore_permissions=True)
        self.assertEqual(doc.status, "Expired")

    def test_rejects_duplicate_national_id(self):
        nid = f"ID{frappe.generate_hash(length=12)}"
        self._doc(national_id_or_iqama=nid).insert(ignore_permissions=True)
        with self.assertRaises(Exception):
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
            fetched.apply_fieldlevel_read_permissions()
            stripped = fetched.as_dict()
            self.assertIsNone(stripped.get("national_id_or_iqama"))
            self.assertIsNone(stripped.get("mobile_number"))
            self.assertEqual(stripped.get("full_name"), "Test Freelancer")
        finally:
            frappe.set_user("Administrator")

    def _user_with_role(self, role):
        """A fresh System User holding exactly one apex role."""
        user = frappe.get_doc(
            {
                "doctype": "User",
                "email": f"freelance_{frappe.generate_hash(length=12)}@example.com",
                "first_name": role.split()[0],
                "roles": [{"role": role}],
            }
        ).insert(ignore_permissions=True)
        return user.name

    def test_only_the_permlevel1_roles_can_create(self):
        """The pair, in one test so the two verdicts cannot collapse into one.

 Finance Manager holds create AND a permlevel-1 write row, so it
        can supply `national_id_or_iqama` and the insert lands. Accommodation
        Manager holds no permlevel-1 row, so its create was REMOVED rather than
        left to fail: `Document.insert` resets the unwritable PII to the
        `frappe.new_doc` value (empty) at document.py:306 before
        `_validate_mandatory` runs at :310, so the button used to raise
        MandatoryError on every single press.

        The refusal is caught by NAME: `frappe.PermissionError` does not descend
        from `ValidationError` (frappe/exceptions.py:34 vs :18), so the old
        MandatoryError could never satisfy this assertion.
        """
        self.addCleanup(frappe.set_user, "Administrator")
        finance = self._user_with_role("Finance Manager")
        housing = self._user_with_role("Accommodation Manager")

        # `has_permission` returns bool(perm) (frappe/permissions.py:193), so `assertIs`
        # is safe and 1 would not pass for True.
        self.assertIs(frappe.has_permission("Freelancer", "create", user=finance), True)
        self.assertIs(frappe.has_permission("Freelancer", "create", user=housing), False)
        # Only create was withdrawn — the housing role still maintains what exists.
        self.assertIs(frappe.has_permission("Freelancer", "read", user=housing), True)
        self.assertIs(frappe.has_permission("Freelancer", "write", user=housing), True)

        nid = f"ID{frappe.generate_hash(length=12)}"

        frappe.set_user(finance)
        created = self._doc(national_id_or_iqama=nid).insert()
        self.assertTrue(created.name.startswith("FRL-"))
        self.assertEqual(
            frappe.db.get_value("Freelancer", created.name, "national_id_or_iqama"),
            nid,
            "the permlevel-1 PII the create depends on must survive the reset pass",
        )
        self.assertIn(
            1,
            created.get_permlevel_access("write"),
            "Finance Manager must reach permlevel 1, or its create only appears to work",
        )

        frappe.set_user(housing)
        refused = self._doc(national_id_or_iqama=f"ID{frappe.generate_hash(length=12)}")
        self.assertNotIn(
            1,
            refused.get_permlevel_access("write"),
            "the housing role holds no permlevel-1 write — the reason create was "
            "removed instead of the PII boundary being widened",
        )
        with self.assertRaises(frappe.PermissionError):
            refused.insert()

    # REMOVED 2026-08-15: test_the_housing_role_can_still_maintain_an_existing_freelance.
    #
    # Test Code Duplication. It built the same Freelancer, made the same Accommodation
    # Manager, made the same `status = "Terminated"` edit and the same save, and read
    # back the same restore-on-update path as
    # test_freelancer_salary_permlevel.py::test_the_housing_role_can_still_save_with_every_level1_field_intact
    # — differing only in which permlevel-1 field it checked survived. That case now
    # carries BOTH fields as subTests, so the national_id_or_iqama verdict this one owned
    # is still asserted, beside the fuller mechanism note (document.py:412 before :414,
    # base_document.py:1288,1291).

    def test_freelance_is_an_accounting_party(self):
        """The core proof: with the custom Party Type registered, a Journal Entry
        can carry party_type='Freelancer' + party=<a freelance>.

 The registration used to be a class-level ``skipUnless``, evaluated
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

        # Built, not skipped on: a fresh CI site's chart is not guaranteed
        # to carry a non-group Payable and Cash account in the company's base
        # currency, and without both there is no Journal Entry to hang the party on.
        company = factories.ensure_company()
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
        je.set_missing_values()
        je.validate()
        self.assertEqual(je.accounts[0].party_type, "Freelancer")
        self.assertEqual(je.accounts[0].party, freelance.name)
