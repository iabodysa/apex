# Copyright (c) 2026, AFMCO and contributors
"""Apex first-install Setup Wizard integration (native Frappe setup wizard).

On a fresh site, Frappe's setup wizard renders an extra "Apex Configuration" slide
(registered by public/js/apex_setup_wizard.js via the `setup_wizard_requires` hook).
The operator's choices flow into the wizard args and land here at completion
(`setup_wizard_complete` hook), where they are applied — ONCE. The GL-posting gate
lands on the Apex Settings single (shared by Habitat and Salis), the chosen payment
target on the Payment Routing Settings single, and the salary deduction toggles on
the Salary Deduction Policy single.

Safe-by-default: a toggle the operator did not tick stays OFF, so the app never
deducts a housing allowance or posts to the GL unless the operator explicitly opts
in during setup. Idempotent: re-running with the same args is harmless.
"""

import frappe
from frappe import _
from frappe.utils import cint


def get_setup_stages(args=None):
    """`setup_wizard_stages` hook — a tracked stage that applies the Apex choices
    during the native wizard's completion sequence."""
    return [
        {
            "status": _("Configuring Apex"),
            "fail_msg": _("Failed to apply the Apex configuration"),
            "tasks": [
                {
                    "fn": apply_apex_setup,
                    "args": args,
                    "fail_msg": _("Failed to apply the Apex configuration"),
                    "app_name": "apex_habitat",
                }
            ],
        }
    ]


def setup_wizard_complete(args=None):
    """`setup_wizard_complete` hook — apply the operator's first-run choices."""
    apply_apex_setup(args)


def apply_apex_setup(args=None):
    """Write the operator's Setup-Wizard choices (create-only semantics on the
    toggles: default OFF unless explicitly chosen). No commit — Frappe commits
    after all setup stages succeed.

    The app-wide ``enable_gl_posting`` finance gate lives on the Apex Settings
    single (it serves both Habitat and Salis); the operator's chosen payment
    target lands on the Payment Routing Settings single (the router that replaced
    the retired ``default_payment_method`` Select); the salary deduction toggles
    live on the Salary Deduction Policy single."""
    args = frappe._dict(args or {})

    payment_method = args.get("apex_default_payment_method")

    # [#55h4xa] The wizard's payment choice is a DocType name; route it to the
    # Payment Routing target, but only when that DocType actually exists on the
    # site (e.g. Expense Request Afmco is an optional client DocType), so the
    # router never points at a missing target.
    if payment_method and frappe.db.exists("DocType", payment_method):
        router = frappe.get_single("Payment Routing Settings")
        router.target_payment_doctype = payment_method
        router.save(ignore_permissions=True)  # audit-ok

    # [#gatccs]
    apex = frappe.get_single("Apex Settings")
    apex.enable_gl_posting = 1 if cint(args.get("apex_post_gl")) else 0
    apex.save(ignore_permissions=True)

    # [#bbeka8]
    deduct_housing = bool(cint(args.get("apex_deduct_housing_allowance")))
    deduct_damage = bool(cint(args.get("apex_deduct_damage")))
    policy = frappe.get_single("Salary Deduction Policy")
    # the global master switch must be on for any per-type rule to fire
    policy.enable_salary_deductions = 1 if (deduct_housing or deduct_damage) else 0
    _set_rule_enabled(policy, "Rent", deduct_housing)
    _set_rule_enabled(policy, "Damage", deduct_damage)
    try:
        policy.save(ignore_permissions=True)
    except frappe.ValidationError:
        # [#44x8l9]
        frappe.clear_last_message()
        policy.reload()
        policy.enable_salary_deductions = 0
        _set_rule_enabled(policy, "Rent", False)
        _set_rule_enabled(policy, "Damage", False)
        policy.save(ignore_permissions=True)
        frappe.msgprint(
            _(
                "Payment method saved. To enable salary deductions, set the "
                "authorizer and salary components on the Salary Deduction Policy "
                "first, then turn the rules on there."
            ),
            title=_("Apex Setup"),
            indicator="orange",
        )


def _set_rule_enabled(policy, rule_type, on):
    """Find-or-create the policy's type rule for ``rule_type`` and set its enabled flag."""
    row = next((r for r in policy.type_rules or [] if r.deduction_type == rule_type), None)
    if row is None:
        if not on:
            return
        row = policy.append("type_rules", {"deduction_type": rule_type})
    row.enabled = 1 if on else 0
