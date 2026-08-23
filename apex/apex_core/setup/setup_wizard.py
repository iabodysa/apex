# Copyright (c) 2026, afmcoltd
"""Apex first-install Setup Wizard integration (native Frappe setup wizard).

The settings saves pass ``ignore_permissions`` because this is installer context: the wizard runs
as Administrator on a fresh site before any operator or role assignment exists. A DocPerm that
made these legal would then let operators edit the same settings afterwards.

On a fresh site, Frappe's setup wizard renders extra "Apex Configuration" slides
(registered by public/js/apex_setup_wizard.js via the `setup_wizard_requires` hook).
The operator's choices flow into the wizard args and land here at completion
(`setup_wizard_complete` hook), where they are applied — ONCE — across every
re-engineered Apex Single:

  - Habitat Settings        — default company, the email/operational kill-switches, the
    app-wide GL-posting finance gate and the Pay-action target payment DocType.
  - Salis Settings          — default company, cost center, driver portal, approvals.
  - native Employee Advance recovery — disabled until payroll/account settings exist.
  - native ERPNext Issue SLA — created only with an operator-selected schedule.

The company and its cost center are NOT among the operator's answers. They are read
from the records ERPNext's own stage created, which run before this hook.

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
from frappe.utils import cint

from apex.apex_core.payment_router import validate_target_doctype
from apex.apex_core.utils.company import resolve_company_or_any

def setup_wizard_complete(args=None):
    """`setup_wizard_complete` hook — apply the operator's first-run choices."""
    apply_apex_setup(args)
    from apex.apex_core.setup.seeders.portal_identity_seed import seed_portal_identities
    from apex.setup import create_accommodation_item_defaults

    seed_portal_identities()
    create_accommodation_item_defaults()

def apply_apex_setup(args=None):
    """Write the operator's Setup-Wizard choices across every Apex Single.

    Skip-safe: a blank/absent field keeps the Single's shipped default (the helpers
    below only write a Link when the arg is present and the target exists). No commit
    — Frappe commits after all setup stages succeed.

    Company and cost center are READ here rather than asked for on the slide. The Apex
    slide carries no Link field at either: Frappe renders every slide before it runs a
    single stage, and ERPNext creates the company in a stage, so a picker would query an
    empty table and force the operator to leave blank a choice he could not make.
    ERPNext's stage runs before this completion hook, so both values already exist."""
    args = frappe._dict(args or {})
    company = resolve_company_or_any()
    cost_center = _created_cost_center(company)

    _apply_payment_routing(args)
    _apply_habitat_settings(args, company)
    _apply_salis_settings(args, company, cost_center)
    _apply_employee_advance_recovery(args, company)
    _apply_salis_support(args)

def _created_cost_center(company):
    """The default cost center ERPNext attached to that company."""
    return frappe.get_cached_value("Company", company, "cost_center") if company else None

def _apply_habitat_settings(args, company):
    """Habitat Settings — default company, the email/operational notification
    kill-switches and the app-wide GL-posting finance gate (default OFF). Company is
    only written when one exists so the Single default holds."""
    habitat = frappe.get_single("Habitat Settings")
    if company:
        habitat.company = company
    habitat.enable_email_notifications = 1 if cint(args.get("apex_enable_email")) else 0
    habitat.enable_operational_notifications = (
        1 if cint(args.get("apex_enable_operational_notifications")) else 0
    )
    habitat.enable_gl_posting = 1 if cint(args.get("apex_post_gl")) else 0
    habitat.save(ignore_permissions=True)

def _apply_salis_settings(args, company, cost_center):
    """Salis Settings — default company + cost center and the driver-portal /
    approvals switches."""
    salis = frappe.get_single("Salis Settings")
    if company:
        salis.default_company = company
    if cost_center:
        salis.default_cost_center = cost_center
    salis.enable_driver_portal = 1 if cint(args.get("apex_enable_driver_portal")) else 0
    if "apex_enable_approvals" in args:
        salis.enable_approvals = 1 if cint(args.get("apex_enable_approvals")) else 0
    salis.save(ignore_permissions=True)

def _apply_payment_routing(args):
    """Habitat Settings — route the operator's chosen payment DocType to the
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
    router = frappe.get_single("Habitat Settings")
    router.target_payment_doctype = payment_method
    router.save(ignore_permissions=True)

def _apply_employee_advance_recovery(args, company):
    """Enable the Apex scheduler only after native HRMS accounts and component exist."""
    from apex.apex_core.setup.employee_advance_recovery import configure_recovery

    configure_recovery(
        enabled=bool(cint(args.get("apex_enable_employee_advance_recovery"))),
        company=company,
        salary_component=args.get("apex_employee_advance_recovery_component"),
        max_percent=args.get("apex_employee_advance_recovery_max_percent"),
    )

def _apply_salis_support(args):
    """Create an Issue SLA only when the setup answers include a complete schedule."""
    from apex.apex_core.setup.salis_support import (
        configure_support_sla,
        ensure_support_holiday_list,
    )

    enabled = bool(cint(args.get("apex_enable_salis_support_sla")))
    if not enabled:
        configure_support_sla(enabled=False)
        return
    holiday_list = ensure_support_holiday_list(
        name=args.get("apex_salis_support_holiday_list"),
        from_date=args.get("apex_salis_support_holiday_from_date"),
        to_date=args.get("apex_salis_support_holiday_to_date"),
        weekly_off=args.get("apex_salis_support_weekly_off"),
        country=args.get("apex_salis_support_country"),
        subdivision=args.get("apex_salis_support_subdivision"),
    )

    configure_support_sla(
        enabled=True,
        holiday_list=holiday_list,
        workdays=args.get("apex_salis_support_workdays"),
        start_time=args.get("apex_salis_support_start_time"),
        end_time=args.get("apex_salis_support_end_time"),
    )
