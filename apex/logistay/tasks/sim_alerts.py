# Copyright (c) 2026, AFMCO and contributors
"""Scheduled SIM alerts.

Complements the two event Notifications (contract expiry via Days Before, a SIM
suspension via the custody Submit event) with a daily standing digest of any SIM
that is still held by a custodian yet sits in a Suspended or Lost status — the
"assigned suspended or lost" watch. One in-app Notification Log per SIM Operations
User per day (no per-SIM spam); re-running re-sends the current snapshot and
mutates nothing.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import escape_html

# Constant name, re-issued each iteration: MariaDB replaces a same-named savepoint
# rather than stacking one per recipient.
_ROW_SAVEPOINT = "sim_alert_row"


def _sim_operations_users():
    """Enabled, real Users holding the SIM Operations User role."""
    users = frappe.get_all(
        "Has Role",
        filters={"role": "SIM Operations User", "parenttype": "User"},
        pluck="parent",
    )
    return [
        u
        for u in set(users)
        if u not in ("Administrator", "Guest") and frappe.db.get_value("User", u, "enabled")
    ]


def assigned_suspended_or_lost_watch() -> None:
    """Daily digest to SIM Operations Users of assigned SIMs that are Suspended or Lost."""
    sims = frappe.get_all(
        "SIM Card",
        filters={
            "status": ["in", ["Suspended", "Lost"]],
            "current_custodian_type": ["!=", "Unassigned"],
        },
        fields=["name", "mobile_number", "status"],
        limit_page_length=0,
    )
    if not sims:
        return

    users = _sim_operations_users()
    if not users:
        return

    subject = _("Assigned SIMs suspended or lost: {0}").format(len(sims))
    body = "<br>".join(
        f"{escape_html(s.mobile_number or s.name)} — {_(s.status)}" for s in sims[:50]
    )
    for user in users:
        frappe.db.savepoint(_ROW_SAVEPOINT)
        try:
            frappe.get_doc(
                {
                    "doctype": "Notification Log",
                    "for_user": user,
                    "type": "Alert",
                    "subject": subject,
                    "email_content": body,
                }
            ).insert(ignore_permissions=True)  # audit-ok — system-raised in-app alert, no user session
        except Exception:
            frappe.db.rollback(save_point=_ROW_SAVEPOINT)
            frappe.log_error(
                title="SIM assigned-suspended digest delivery failed",
                message=frappe.get_traceback(),
            )
