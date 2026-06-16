"""Server-side guard for the Apex first-install Setup Wizard.

The JS slide (public/js/apex_setup_wizard.js) renders only on a fresh site and is
browser-verified by the operator. The APPLY logic is verified here: the payment
method is set, and the deduction/GL toggles are applied SAFELY — they stay OFF when
their prerequisites (an authorizer, accounts) are missing, so the wizard never
fails and the app never silently starts deducting at first install.
"""

import unittest

import frappe
from frappe.tests.utils import FrappeTestCase

from apex_habitat.apex_core.setup.setup_wizard import setup_wizard_complete


class TestApexSetupWizard(FrappeTestCase):
    def test_payment_method_applies_and_toggles_stay_safe(self):
        # [#ql6hkn]
        setup_wizard_complete(
            {
                "apex_default_payment_method": "Payment Order",
                "apex_deduct_housing_allowance": 1,
                "apex_deduct_damage": 1,
            }
        )
        s = frappe.get_single("Habitat Settings")
        apex = frappe.get_single("Apex Settings")
        self.assertEqual(apex.default_payment_method, "Payment Order")
        self.assertEqual(s.enable_housing_allowance_deduction, 0)  # [#pnt7gf]
        self.assertEqual(apex.enable_gl_posting, 0)
        self.assertEqual(s.enable_damage_deduction, 0)

    def test_toggles_off_when_not_chosen(self):
        setup_wizard_complete({"apex_default_payment_method": "Payment Entry"})
        s = frappe.get_single("Habitat Settings")
        apex = frappe.get_single("Apex Settings")
        self.assertEqual(apex.default_payment_method, "Payment Entry")
        self.assertEqual(s.enable_housing_allowance_deduction, 0)
        self.assertEqual(apex.enable_gl_posting, 0)

    def test_no_args_is_safe(self):
        setup_wizard_complete()  # [#agr94p]
        s = frappe.get_single("Habitat Settings")
        self.assertEqual(s.enable_housing_allowance_deduction, 0)


if __name__ == "__main__":
    unittest.main()
