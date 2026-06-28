# Copyright (c) 2026, AFMCO and contributors
"""Server-side guard for the Apex first-install Setup Wizard.

The JS slide (public/js/apex_setup_wizard.js) renders only on a fresh site and is
browser-verified by the operator. The APPLY logic is verified here: the chosen
payment target lands on the Payment Routing Settings router (the Select that
replaced the retired default_payment_method), and the deduction/GL toggles are
applied SAFELY — they stay OFF when their prerequisites (an authorizer, accounts)
are missing, so the wizard never fails and the app never silently starts deducting
at first install.
"""

import unittest

import frappe
from frappe.tests.utils import FrappeTestCase

from apex_habitat.apex_core.setup.setup_wizard import setup_wizard_complete


def _rule_enabled(policy, rule_type):
    """The enabled flag of the policy's type rule for ``rule_type`` (0 if absent)."""
    row = next((r for r in policy.type_rules or [] if r.deduction_type == rule_type), None)
    return row.enabled if row else 0


class TestApexSetupWizard(FrappeTestCase):
    def test_payment_method_routes_to_router_and_toggles_stay_safe(self):
        # [#ql6hkn] "Payment Order" is a core ERPNext DocType, so it exists and the
        # wizard routes it onto the Payment Routing target.
        setup_wizard_complete(
            {
                "apex_default_payment_method": "Payment Order",
                "apex_deduct_housing_allowance": 1,
                "apex_deduct_damage": 1,
            }
        )
        policy = frappe.get_single("Salary Deduction Policy")
        apex = frappe.get_single("Apex Settings")
        router = frappe.get_single("Payment Routing Settings")
        self.assertEqual(router.target_payment_doctype, "Payment Order")
        # [#pnt7gf] prerequisites (authorizer / component) missing -> wizard reverts
        # the deductions to OFF safely; the app never silently starts deducting
        self.assertEqual(policy.enable_salary_deductions, 0)
        self.assertEqual(_rule_enabled(policy, "Rent"), 0)
        self.assertEqual(_rule_enabled(policy, "Damage"), 0)
        self.assertEqual(apex.enable_gl_posting, 0)

    def test_toggles_off_when_not_chosen(self):
        setup_wizard_complete({"apex_default_payment_method": "Payment Entry"})
        policy = frappe.get_single("Salary Deduction Policy")
        apex = frappe.get_single("Apex Settings")
        router = frappe.get_single("Payment Routing Settings")
        self.assertEqual(router.target_payment_doctype, "Payment Entry")
        self.assertEqual(policy.enable_salary_deductions, 0)
        self.assertEqual(_rule_enabled(policy, "Rent"), 0)
        self.assertEqual(apex.enable_gl_posting, 0)

    def test_no_args_is_safe(self):
        setup_wizard_complete()  # [#agr94p]
        policy = frappe.get_single("Salary Deduction Policy")
        self.assertEqual(policy.enable_salary_deductions, 0)
        self.assertEqual(_rule_enabled(policy, "Rent"), 0)


if __name__ == "__main__":
    unittest.main()
