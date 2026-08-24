# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import add_to_date, cint, nowdate, today

from apex.apex_core.utils.system_notify import notify_user_system
from apex.logistay import permissions
from apex.logistay.utils.roles import sim_operations_users

_ROW_SAVEPOINT = "telecom_contract_expiry_row"


def _contract_expiry_notice_days() -> int:
    return cint(frappe.db.get_single_value("Logistay Settings", "contract_expiry_notice_days")) or 30


def contract_expiry_watch() -> None:
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
    reference_date = add_to_date(nowdate(), days=_contract_expiry_notice_days())
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
