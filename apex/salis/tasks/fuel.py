# Copyright (c) 2026, AFMCO and contributors
"""Scheduled tasks for the Salis fleet module (split by domain)."""

from __future__ import annotations

import frappe
from frappe import _

from apex.salis.tasks.common import (
    ALERT_DOCTYPE,
    BATCH_SIZE,
    _raise_alert,
    _resolve_alert,
    _settings_int,
)

_ROW_SAVEPOINT = "salis_fuel_row"

_RESOLVE_SAVEPOINT = "salis_topup_resolve"


def unreverted_topup_watch() -> None:
    """Auto-revert temporary fuel top-ups that are past their revert-due date,
    then raise an alert for each.

    Reads Fuel Request ``{request_type: Top-up, is_temporary: 1, reverted: 0,
    status in [Approved, Done], revert_due_date: < today}``. For each overdue
    row it loads the document, sets ``reverted = 1`` and ``status = Reverted``,
    saves it (the change is captured natively by Version / track_changes), and
    still raises a Critical "Excessive Topup" alert.

    Each row is guarded in its own ``try/except`` (rollback + log) so one
    failure never aborts the batch. No ``commit()`` inside the loop — the
    scheduler commits the job transaction on success.
    """
    from frappe.utils import today

    today_str = today()
    logger = frappe.logger()

    cursor = ""
    while True:
        topups = frappe.get_all(
            "Fuel Request",
            filters={
                "request_type": "Top-up",
                "is_temporary": 1,
                "reverted": 0,
                "status": ["in", ["Approved", "Done"]],
                "revert_due_date": ["<", today_str],
                "name": [">", cursor],
            },
            fields=["name", "vehicle", "driver", "revert_due_date", "topup_litres"],
            order_by="name asc",
            limit_page_length=BATCH_SIZE,
        )
        if not topups:
            break

        for t in topups:
            frappe.db.savepoint(_ROW_SAVEPOINT)
            try:
                doc = frappe.get_doc("Fuel Request", t.name)
                doc.reverted = 1
                doc.status = "Reverted"
                doc.save(ignore_permissions=True)  # audit-ok
                doc.add_comment(
                    "Info",
                    _("Auto-reverted: overdue temporary top-up (was due {0}).").format(
                        t.revert_due_date
                    ),
                )

                msg = (f"unreverted_topup_watch: temporary top-up {t.name} "
                       f"({t.topup_litres} L) was due to be reverted on "
                       f"{t.revert_due_date}; it has now been auto-reverted.")
                logger.warning(msg)
                _raise_alert("Excessive Topup", "Critical", msg,
                             "Fuel Request", t.name,
                             vehicle=t.vehicle, driver=t.driver)
            except Exception:
                frappe.db.rollback(save_point=_ROW_SAVEPOINT)
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=f"Unreverted top-up watch failed for {t.name}"[:140],
                )

        cursor = topups[-1].name


def overdue_fuel_request_watch() -> None:
    """Flag fuel requests stuck in Pending past ``fuel_pending_max_days``.

    Reads submitted Fuel Request ``{status: Pending}`` whose ``request_date`` is
    older than ``fuel_pending_max_days`` (Salis Settings; default 2) and raises
    a Warning "Forgotten Request" alert per row.
    """
    from frappe.utils import add_days, date_diff, today

    today_str = today()
    logger = frappe.logger()
    max_days = _settings_int("fuel_pending_max_days", 2)
    cutoff = add_days(today_str, -max_days)

    start = 0
    while True:
        requests = frappe.get_all(
            "Fuel Request",
            filters={
                "status": "Pending",
                "docstatus": 1,
                "request_date": ["<", cutoff],
            },
            fields=["name", "vehicle", "driver", "request_date"],
            limit_start=start,
            limit_page_length=BATCH_SIZE,
        )
        if not requests:
            break

        for r in requests:
            frappe.db.savepoint(_ROW_SAVEPOINT)
            try:
                age = date_diff(today_str, r.request_date) if r.request_date else 0
                msg = (f"overdue_fuel_request_watch: fuel request {r.name} has been "
                       f"Pending for {age} days (since {r.request_date}).")
                logger.warning(msg)
                _raise_alert("Forgotten Request", "Warning", msg,
                             "Fuel Request", r.name,
                             vehicle=r.vehicle, driver=r.driver)
            except Exception:
                frappe.db.rollback(save_point=_ROW_SAVEPOINT)
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=f"Overdue fuel request watch failed for {r.name}"[:140],
                )

        start += BATCH_SIZE


def resolve_excessive_topup_alerts(vehicle: str | None, reason: str) -> int:
    """Resolve any open/acknowledged ``Excessive Topup`` alert for ``vehicle``.

    Event-driven counterpart to the periodic resolver: callers fire this from a
    clean source event (e.g. a temporary top-up is reverted) so the alert clears
    immediately rather than waiting for the next daily reconciliation pass. Safe
    to call even when no matching alert exists (returns 0) and idempotent
    (already-Resolved rows are filtered out). Never raises: a failure rolls back only
    to this call's own savepoint and is logged, so it can neither raise into nor
    discard the source-document save that triggered it.

    Returns the number of alerts this call resolved.
    """
    if not vehicle:
        return 0
    resolved = 0
    frappe.db.savepoint(_RESOLVE_SAVEPOINT)
    try:
        open_alerts = frappe.get_all(
            ALERT_DOCTYPE,
            filters={
                "alert_type": "Excessive Topup",
                "vehicle": vehicle,
                "status": ["in", ["Open", "Acknowledged"]],
            },
            pluck="name",
        )
        for name in open_alerts:
            if _resolve_alert(name, reason):
                resolved += 1
    except Exception:
        frappe.db.rollback(save_point=_RESOLVE_SAVEPOINT)
        frappe.log_error(
            message=frappe.get_traceback(),
            title=f"Excessive-topup alert resolve-on-event failed ({vehicle})"[:140],
        )
    return resolved
