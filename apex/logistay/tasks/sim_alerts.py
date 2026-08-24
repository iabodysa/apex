# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import escape_html

from apex.apex_core.utils.system_notify import notify_user_system
from apex.logistay import permissions
from apex.logistay.utils.roles import sim_operations_users

_FIELDS = ["name", "mobile_number", "status"]


def _watchlist(companies) -> list:
    scope = {} if companies is None else {"company": ["in", companies]}
    suspended = frappe.get_all(
        "SIM Card",
        filters={
            **scope,
            "status": "Suspended",
            "current_custodian_type": ["!=", "Unassigned"],
        },
        fields=_FIELDS,
        limit_page_length=0,
    )
    lost = frappe.get_all(
        "SIM Card",
        filters={**scope, "status": "Lost"},
        fields=_FIELDS,
        limit_page_length=0,
    )
    return suspended + lost


def assigned_suspended_or_lost_watch() -> None:
    for user in sim_operations_users():
        restrict, allowed = permissions.report_company_scope(user, doctype="SIM Card")
        if restrict and not allowed:
            continue
        sims = _watchlist(allowed if restrict else None)
        if not sims:
            continue
        subject = _("Assigned SIMs suspended or lost: {0}").format(len(sims))
        body = "<br>".join(
            f"{escape_html(s.mobile_number or s.name)} — {_(s.status)}" for s in sims[:50]
        )
        notify_user_system(user, subject, body)
