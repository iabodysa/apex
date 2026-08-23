# Copyright (c) 2026, afmcoltd
"""Scheduled SIM alerts.

Complements the two event Notifications (contract expiry via Days Before, a SIM
suspension via the custody Submit event) with a daily standing digest of any SIM
that is still held by a custodian yet sits in a Suspended status, plus every Lost
SIM — the "assigned suspended or lost" watch. One in-app Notification Log per SIM
Operations User per day (no per-SIM spam); re-running re-sends the current snapshot
and mutates nothing.

The digest is built PER RECIPIENT, not broadcast. ``frappe.get_all`` hardcodes
``ignore_permissions=True`` (frappe/__init__.py:2050), so the
``permission_query_conditions`` entry that scopes SIM Card to a user's companies
never applies to a scheduled read — one shared body would hand a user scoped to
company A the MSISDNs of company B. Each user's companies are resolved with the
module's own ``report_company_scope`` and pushed into the filter.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import escape_html

from apex.apex_core.utils.system_notify import notify_user_system
from apex.logistay import permissions
from apex.logistay.utils.roles import sim_operations_users

_FIELDS = ["name", "mobile_number", "status"]


def _watchlist(companies) -> list:
    """Suspended SIMs still in a custodian's hands, plus every Lost SIM.

    Two queries, not one ``status in (Suspended, Lost)`` filter, because a Lost SIM has
    no custodian left to require: retirement is an event in the custody chain and the
    replay clears ``current_custodian_type`` to Unassigned on it
    (sim_custody_assignment._apply_event). A single filter demanding a live custodian
    therefore excludes precisely the SIMs the watch exists to raise.

    ``companies`` is None for an oversight role (no company restriction) or the list the
    recipient is permitted to see.
    """
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
    """Daily per-recipient digest of held-but-Suspended SIMs and every Lost SIM."""
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
