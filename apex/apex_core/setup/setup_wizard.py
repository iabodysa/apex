# Copyright (c) 2026, afmcoltd

import frappe
from frappe.utils import cint

from apex.apex_core.payment_router import validate_target_doctype
from apex.apex_core.setup.employee_advance_recovery import configure_recovery
from apex.apex_core.setup.salis_support import (
    configure_support_sla,
    ensure_support_holiday_list,
)
from apex.apex_core.setup.seeders.portal_identity_seed import seed_portal_identities
from apex.apex_core.utils.company import resolve_company_or_any
from apex.setup import create_accommodation_item_defaults

def setup_wizard_complete(args=None):
    apply_apex_setup(args)
    seed_portal_identities()
    create_accommodation_item_defaults()

def apply_apex_setup(args=None):
    args = frappe._dict(args or {})
    company = resolve_company_or_any()
    cost_center = _created_cost_center(company)

    _apply_payment_routing(args)
    _apply_habitat_settings(args, company)
    _apply_salis_settings(args, company, cost_center)
    _apply_employee_advance_recovery(args, company)
    _apply_salis_support(args)

def _created_cost_center(company):
    return frappe.get_cached_value("Company", company, "cost_center") if company else None

def _apply_habitat_settings(args, company):
    habitat = frappe.get_single("Habitat Settings")
    if company:
        habitat.company = company
    habitat.enable_email_notifications = 1 if cint(args.get("apex_enable_email")) else 0
    habitat.enable_operational_notifications = (
        1 if cint(args.get("apex_enable_operational_notifications")) else 0
    )
    habitat.enable_gl_posting = 1 if cint(args.get("apex_post_gl")) else 0
    habitat.save()

def _apply_salis_settings(args, company, cost_center):
    salis = frappe.get_single("Salis Settings")
    if company:
        salis.default_company = company
    if cost_center:
        salis.default_cost_center = cost_center
    salis.enable_driver_portal = 1 if cint(args.get("apex_enable_driver_portal")) else 0
    if "apex_enable_approvals" in args:
        salis.enable_approvals = 1 if cint(args.get("apex_enable_approvals")) else 0
    salis.save()

def _apply_payment_routing(args):
    payment_method = (args.get("apex_default_payment_method") or "").strip()
    if not payment_method:
        return
    validate_target_doctype(payment_method)
    router = frappe.get_single("Habitat Settings")
    router.target_payment_doctype = payment_method
    router.save()

def _apply_employee_advance_recovery(args, company):
    configure_recovery(
        enabled=bool(cint(args.get("apex_enable_employee_advance_recovery"))),
        company=company,
        salary_component=args.get("apex_employee_advance_recovery_component"),
        max_percent=args.get("apex_employee_advance_recovery_max_percent"),
    )

def _apply_salis_support(args):
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
