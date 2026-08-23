# Copyright (c) 2026, afmcoltd
"""Scheduled Telecom Contract status maintenance and expiry notice.

``TelecomContract._sync_status`` derives Active vs Expired from the contract
period, but only inside ``validate``, and Frappe never runs ``validate`` again
on a submitted document. A contract that is Active the day it is submitted
therefore stays Active forever once its own ``contract_end_date`` passes,
unless something re-derives the status later — this is that later
re-derivation, the same shape as Habitat's ``lease_expiry_watchlist``
(apex/habitat/tasks/residency.py).

``contract_expiry_soon_watch`` replaces the shipped "SIM Operations - Contract
Expiry Soon" Notification (Days Before, disabled), which resolved every SIM
Operations User site-wide through ``receiver_by_role`` — a company-scoped user
was alerted about every other company's contracts, because
``get_info_based_on_role`` runs ``ignore_permissions``. Same
``report_company_scope`` narrowing as ``sim_alerts.py``'s daily digest, and
the same 30-day match Frappe's own ``Notification.get_documents_for_today``
used (``contract_end_date`` falling on today + 30, matched by full day).
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import add_to_date, nowdate, today

from apex.apex_core.utils.system_notify import notify_user_system
from apex.logistay import permissions
from apex.logistay.utils.roles import sim_operations_users

_ROW_SAVEPOINT = "telecom_contract_expiry_row"
CONTRACT_EXPIRY_NOTICE_DAYS = 30


def contract_expiry_watch() -> None:
    """Flip every submitted, still-Active contract whose end date has passed to Expired.

    A direct field write, not a re-``save()``: ``status`` is read-only and
    derived, so this mirrors the same out-of-workflow write ``on_cancel``
    already uses for Terminated. Terminated contracts are never matched by the
    ``status == "Active"`` filter, so retirement is never overwritten here.
    """
    today_str = today()
    cursor = ""
    batch_size = 500
    while True:
        contracts = frappe.get_all(
            "Telecom Contract",
            filters={
                "docstatus": 1,
                "status": "Active",
                "contract_end_date": ["<", today_str],
                "name": [">", cursor],
            },
            fields=["name"],
            order_by="name asc",
            limit_page_length=batch_size,
        )
        if not contracts:
            break

        for contract in contracts:
            frappe.db.savepoint(_ROW_SAVEPOINT)
            try:
                frappe.db.set_value("Telecom Contract", contract.name, "status", "Expired")
            except Exception:
                frappe.db.rollback(save_point=_ROW_SAVEPOINT)
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=f"Telecom contract expiry watch failed for {contract.name}"[:140],
                )

        cursor = contracts[-1].name


def contract_expiry_soon_watch() -> None:
    """Notify each SIM Operations User, scoped to their own company, of every
    submitted Active contract whose end date falls exactly
    ``CONTRACT_EXPIRY_NOTICE_DAYS`` from today."""
    reference_date = add_to_date(nowdate(), days=CONTRACT_EXPIRY_NOTICE_DAYS)
    contracts = frappe.get_all(
        "Telecom Contract",
        filters={
            "docstatus": 1,
            "status": "Active",
            "contract_end_date": reference_date,
        },
        fields=["name", "supplier", "contract_end_date", "company"],
        limit_page_length=0,
    )
    if not contracts:
        return

    for user in sim_operations_users():
        restrict, allowed = permissions.report_company_scope(user, doctype="Telecom Contract")
        rows = (
            [c for c in contracts if c.company in (allowed or [])] if restrict else contracts
        )
        if not rows:
            continue
        subject = _("Telecom contracts expiring soon: {0}").format(len(rows))
        body = "<br>".join(
            f"{frappe.utils.escape_html(c.name)} ({frappe.utils.escape_html(c.supplier)}) "
            f"— {_('ends')} {c.contract_end_date}"
            for c in rows[:50]
        )
        notify_user_system(user, subject, body)
