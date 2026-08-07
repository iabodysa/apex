# Copyright (c) 2026, afmcoltd
"""Apex first-install Setup Wizard integration (native Frappe setup wizard).

On a fresh site, Frappe's setup wizard renders extra "Apex Configuration" slides
(registered by public/js/apex_setup_wizard.js via the `setup_wizard_requires` hook).
The operator's choices flow into the wizard args and land here at completion
(`setup_wizard_complete` hook), where they are applied — ONCE — across every
re-engineered Apex Single:

  - Apex Settings           — the app-wide GL-posting finance gate.
  - Habitat Settings        — default company + the email/operational kill-switches.
  - Salis Settings          — default company, cost center, driver portal, approvals.
  - Salary Deduction Policy  — the housing/damage deduction toggles + posting company.
  - Payment Routing Settings — the Pay-action target payment DocType.

Safe-by-default + skip-safe: a field the operator leaves blank (or a toggle left
at its pre-filled value) keeps the Single's own default — the wizard never writes
a phantom value. The deduction master switch and the GL gate stay OFF unless the
operator explicitly opts in. Idempotent: re-running with the same args is harmless.

Skip-safe is NOT fail-open: a payment target the operator actually named but that
cannot build a payment stops setup with an actionable message rather than being
dropped, because a dropped choice leaves the router pointing somewhere the
operator never picked.
"""

import frappe
from frappe import _
from frappe.utils import cint

from apex.apex_core.payment_router import validate_target_doctype

from apex.apex_core.utils.system_write import system_save


def setup_wizard_complete(args=None):
    """`setup_wizard_complete` hook — apply the operator's first-run choices."""
    apply_apex_setup(args)
    from apex.setup import create_accommodation_item_defaults

    create_accommodation_item_defaults()


def apply_apex_setup(args=None):
    """Write the operator's Setup-Wizard choices across every Apex Single.

    Skip-safe: a blank/absent field keeps the Single's shipped default (the helpers
    below only write a Link when the arg is present and the target exists). No commit
    — Frappe commits after all setup stages succeed."""
    args = frappe._dict(args or {})

    _apply_payment_routing(args)
    _apply_apex_settings(args)
    _apply_habitat_settings(args)
    _apply_salis_settings(args)
    _apply_deduction_policy(args)


def _apply_apex_settings(args):
    """Apex Settings — the app-wide GL-posting finance gate (default OFF)."""
    apex = frappe.get_single("Apex Settings")
    apex.enable_gl_posting = 1 if cint(args.get("apex_post_gl")) else 0
    system_save(apex)


def _apply_habitat_settings(args):
    """Habitat Settings — default company + the email/operational notification
    kill-switches. Company is only written when chosen so the Single default holds."""
    habitat = frappe.get_single("Habitat Settings")
    company = args.get("apex_default_company")
    if company and frappe.db.exists("Company", company):
        habitat.company = company
    habitat.enable_email_notifications = 1 if cint(args.get("apex_enable_email")) else 0
    habitat.enable_operational_notifications = (
        1 if cint(args.get("apex_enable_operational_notifications")) else 0
    )
    system_save(habitat)


def _apply_salis_settings(args):
    """Salis Settings — default company + cost center (write-when-chosen) and the
    driver-portal / approvals switches."""
    salis = frappe.get_single("Salis Settings")
    company = args.get("apex_default_company")
    if company and frappe.db.exists("Company", company):
        salis.default_company = company
    cost_center = args.get("apex_default_cost_center")
    if cost_center and frappe.db.exists("Cost Center", cost_center):
        salis.default_cost_center = cost_center
    salis.enable_driver_portal = 1 if cint(args.get("apex_enable_driver_portal")) else 0
    salis.enable_approvals = 1 if cint(args.get("apex_enable_approvals")) else 0
    system_save(salis)


def _apply_payment_routing(args):
    """Payment Routing Settings — route the operator's chosen payment DocType to the
    Pay-action target, REFUSING anything that cannot be a payment document.

    Blank keeps the native Payment Request default. A named target is validated by
    the router's own guard and the setup fails loudly if it does not hold: silently
    dropping the choice (the previous behaviour when e.g. the optional Expense
    Request Afmco DocType was absent) let setup report success while every later
    payment was built as a different document than the operator selected."""
    payment_method = (args.get("apex_default_payment_method") or "").strip()
    if not payment_method:
        return
    validate_target_doctype(payment_method)
    router = frappe.get_single("Payment Routing Settings")
    router.target_payment_doctype = payment_method
    system_save(router)


def _apply_deduction_policy(args):
    """Salary Deduction Policy — the housing/damage deduction toggles (default OFF)
    plus the posting company. The global master switch only turns on if at least one
    per-type rule is enabled."""
    deduct_housing = bool(cint(args.get("apex_deduct_housing_allowance")))
    deduct_damage = bool(cint(args.get("apex_deduct_damage")))
    company = args.get("apex_default_company")

    policy = frappe.get_single("Salary Deduction Policy")
    if company and frappe.db.exists("Company", company):
        policy.company = company
    policy.enable_salary_deductions = 1 if (deduct_housing or deduct_damage) else 0
    _set_rule_enabled(policy, "Rent", deduct_housing)
    _set_rule_enabled(policy, "Damage", deduct_damage)
    try:
        system_save(policy)
    except frappe.ValidationError:
        frappe.clear_last_message()
        policy.reload()
        policy.enable_salary_deductions = 0
        _set_rule_enabled(policy, "Rent", False)
        _set_rule_enabled(policy, "Damage", False)
        system_save(policy)
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
