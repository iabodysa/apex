# Copyright (c) 2026, AFMCO and contributors
"""Server-side guard for the Apex first-install Setup Wizard.

The JS slide (public/js/apex_setup_wizard.js) renders only on a fresh site and is
browser-verified by the operator. The APPLY logic is verified here: the chosen
payment target lands on the Payment Routing Settings router (the Select that
replaced the retired default_payment_method), and the deduction/GL toggles are
applied SAFELY — they stay OFF when their prerequisites (an authorizer, accounts)
are missing, so the wizard never fails and the app never silently starts deducting
at first install.

Safe-by-default is not the same as fail-open, and the second half of this file draws
that line: a toggle whose prerequisites are missing stays OFF, but a payment target
the operator actually NAMED and that cannot build a payment stops setup with a
message, because dropping it silently pointed the router somewhere they never chose.
"""

import unittest

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.apex_core.setup.setup_wizard import setup_wizard_complete

ROUTER = "Payment Routing Settings"
FIELD_MAP_CHILD = "Payment Routing Field Map"


def _rule_enabled(policy, rule_type):
    """The enabled flag of the policy's type rule for ``rule_type`` (0 if absent)."""
    row = next((r for r in policy.type_rules or [] if r.deduction_type == rule_type), None)
    return row.enabled if row else 0


class TestApexSetupWizard(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        # Setup re-points the router's TARGET, so any field map inherited from another
        # module is left describing a DocType nobody chose here and is refused against
        # the new target. A fresh install has no rows; start from that.
        frappe.db.delete(FIELD_MAP_CHILD, {"parent": ROUTER})
        frappe.db.set_single_value(ROUTER, "target_payment_doctype", None)

    def test_payment_method_routes_to_router_and_toggles_stay_safe(self):
        # [#p21yh6]
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
        # [#e5daxc]
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

    def test_setup_refuses_a_payment_target_the_site_does_not_have(self):
        """The fail-open this guard exists for.

        Setup used to DROP a chosen target it could not find and report success, so
        the router stayed on the native default while the operator believed their
        choice had applied — every later payment built as a different document than
        the one they picked, with nothing anywhere saying so. The valid choice must
        still apply, or the refusal proves nothing.
        """
        setup_wizard_complete({"apex_default_payment_method": "Payment Entry"})
        self.assertEqual(
            frappe.get_single(ROUTER).target_payment_doctype, "Payment Entry"
        )

        ghost = "Apex A278 Absent Payment DocType"
        self.assertFalse(frappe.db.exists("DocType", ghost))
        with self.assertRaises(frappe.ValidationError) as cm:
            setup_wizard_complete({"apex_default_payment_method": ghost})
        self.assertIn(ghost, str(cm.exception))
        self.assertIn("not installed", str(cm.exception))
        # Refused before anything was written, so the previous routing still stands.
        self.assertEqual(
            frappe.get_single(ROUTER).target_payment_doctype, "Payment Entry"
        )

    def test_setup_refuses_a_single_as_the_payment_target(self):
        """A Single is a real DocType, so it passes every existence check and only a
        structural guard stops it — creating one overwrites that settings record."""
        setup_wizard_complete({"apex_default_payment_method": "Payment Entry"})
        self.assertEqual(
            frappe.get_single(ROUTER).target_payment_doctype, "Payment Entry"
        )

        with self.assertRaises(frappe.ValidationError) as cm:
            setup_wizard_complete({"apex_default_payment_method": "Apex Settings"})
        self.assertIn("Single", str(cm.exception))
        self.assertEqual(
            frappe.get_single(ROUTER).target_payment_doctype, "Payment Entry"
        )

    def test_blank_payment_target_stays_skip_safe(self):
        """Fail-closed applies to a choice the operator MADE. Leaving the field blank
        is not a mistake, so it must neither refuse nor overwrite."""
        setup_wizard_complete({"apex_default_payment_method": "Payment Entry"})
        setup_wizard_complete({"apex_default_payment_method": ""})
        self.assertEqual(
            frappe.get_single(ROUTER).target_payment_doctype, "Payment Entry"
        )


if __name__ == "__main__":
    unittest.main()
