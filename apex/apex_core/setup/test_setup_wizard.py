# Copyright (c) 2026, AFMCO and contributors
"""Server-side guard for the Apex first-install Setup Wizard.

The JS slide (public/js/apex_setup_wizard.js) renders only on a fresh site and is
browser-verified by the operator. The APPLY logic is verified here: the chosen
payment target lands on the Payment Routing Settings router (the Select that
replaced the retired default_payment_method), and native Employee Advance
recovery (apex_core/setup/employee_advance_recovery.py:configure_recovery) is
applied SAFELY — it stays OFF when the operator leaves it unset, so the wizard
never fails and the app never silently starts deducting at first install.

Safe-by-default is not the same as fail-open, and the second half of this file draws
that line: a toggle the operator never asked for stays OFF, but a choice they actually
MADE — a payment target that cannot build a payment, or recovery activated without a
Receivable Default Employee Advance Account on the Company
(apex_core/setup/employee_advance_recovery.py:66-75) — stops setup with a message,
because dropping it silently pointed the router or the deduction somewhere they never
chose.
"""

import unittest

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.apex_core.setup.setup_wizard import setup_wizard_complete

ROUTER = "Payment Routing Settings"
FIELD_MAP_CHILD = "Payment Routing Field Map"


class TestApexSetupWizard(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        # Setup re-points the router's TARGET, so any field map inherited from another
        # module is left describing a DocType nobody chose here and is refused against
        # the new target. A fresh install has no rows; start from that.
        frappe.db.delete(FIELD_MAP_CHILD, {"parent": ROUTER})
        frappe.db.set_single_value(ROUTER, "target_payment_doctype", None)

    def test_payment_method_routes_to_router_and_toggles_stay_safe(self):
        """Recovery requested without a Receivable Default Employee Advance Account
        refuses loudly (employee_advance_recovery.py:66-75) rather than silently
        landing OFF -- the same skip-safe-is-not-fail-open contract the payment
        router draws below. The router still applies: each Single is saved as its
        own step runs, so the earlier payment-routing step is not undone by a later
        step's refusal."""
        company = frappe.defaults.get_global_default("company") or frappe.db.get_value(
            "Company", {}
        )
        original_account = frappe.db.get_value(
            "Company", company, "default_employee_advance_account"
        )
        frappe.db.set_value("Company", company, "default_employee_advance_account", None)
        self.addCleanup(
            frappe.db.set_value,
            "Company",
            company,
            "default_employee_advance_account",
            original_account,
        )

        with self.assertRaises(frappe.ValidationError) as cm:
            setup_wizard_complete(
                {
                    "apex_default_payment_method": "Payment Order",
                    "apex_enable_employee_advance_recovery": 1,
                }
            )
        self.assertIn("Default Employee Advance Account", str(cm.exception))

        policy = frappe.get_single("Salis Settings")
        apex = frappe.get_single("Apex Settings")
        router = frappe.get_single(ROUTER)
        self.assertEqual(router.target_payment_doctype, "Payment Order")
        self.assertEqual(policy.enable_employee_advance_recovery, 0)
        self.assertEqual(apex.enable_gl_posting, 0)

    def test_toggles_off_when_not_chosen(self):
        setup_wizard_complete({"apex_default_payment_method": "Payment Entry"})
        policy = frappe.get_single("Salis Settings")
        apex = frappe.get_single("Apex Settings")
        router = frappe.get_single(ROUTER)
        self.assertEqual(router.target_payment_doctype, "Payment Entry")
        self.assertEqual(policy.enable_employee_advance_recovery, 0)
        self.assertEqual(apex.enable_gl_posting, 0)

    def test_no_args_is_safe(self):
        setup_wizard_complete()
        policy = frappe.get_single("Salis Settings")
        self.assertEqual(policy.enable_employee_advance_recovery, 0)

    def test_setup_refuses_a_payment_target_the_site_does_not_have(self):
        """The fail-open this guard exists for.

        Without this guard, setup DROPS a chosen target it cannot find and reports
        success, so the router stays on the native default while the operator believes
        their choice applied — every later payment builds as a different document than
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
