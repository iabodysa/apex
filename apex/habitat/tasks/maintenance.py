# Copyright (c) 2026, AFMCO and contributors
"""Scheduled tasks for the Habitat module (split by domain)."""

from __future__ import annotations

import frappe

from apex.apex_core.utils.operations_alert import insert_operations_alert

# One savepoint per nesting level, distinct names: _raise_maintenance_alert runs
# INSIDE the escalation loop, so re-using the loop's name there would replace it
# mid-iteration and silently destroy the row isolation.
_ROW_SAVEPOINT = "maintenance_row"
_ALERT_SAVEPOINT = "maintenance_alert"


def daily_building_license_expiry_check() -> None:
    """Flip Building License status to Expired / Expiring Soon on the transition edge.

    Operator alerting is owned by the native Notifications ``Habitat - Building
    License Expiring Soon`` and ``Habitat - Building License Expired`` (P-204). This
    job carries ONLY the residual status flip those Notifications cannot perform:
    ``set_property_after_alert`` is a no-op on a submitted document whose ``status``
    field is not ``allow_on_submit`` (Building License is submitted), and it cannot
    honour the per-record ``renewal_lead_days`` override. So the sweep is kept —
    stripped of the old notify/message boilerplate — purely to keep the persisted
    status accurate (Active/Expiring Soon are swept; Expired/Revoked are left alone).
    """
    from frappe.utils import date_diff, today

    today_str = today()

    # [#bz69zh] Keyed cursor, not an offset: the body flips status OUT of the very
    # set this filters on, so rows behind an offset shift down into the range it just
    # passed and are skipped. name is immutable, so a key cursor cannot lose a row.
    cursor = ""
    batch_size = 500
    while True:
        licenses = frappe.get_all(
            "Building License",
            filters={
                "docstatus": 1,
                "status": ["in", ["Active", "Expiring Soon"]],
                "name": [">", cursor],
            },
            fields=["name", "expiry_date", "renewal_lead_days", "status"],
            order_by="name asc",
            limit_page_length=batch_size,
        )
        if not licenses:
            break

        default_lead = frappe.db.get_single_value("Habitat Settings", "license_expiry_days_before") or 60
        for lic in licenses:
            if not lic.expiry_date:
                continue

            frappe.db.savepoint(_ROW_SAVEPOINT)
            try:
                lead_days = lic.renewal_lead_days if lic.renewal_lead_days is not None else default_lead
                days_to_expiry = date_diff(lic.expiry_date, today_str)

                if days_to_expiry <= 0:
                    if lic.status != "Expired":
                        frappe.db.set_value("Building License", lic.name, "status", "Expired")
                elif days_to_expiry <= lead_days:
                    if lic.status != "Expiring Soon":
                        frappe.db.set_value("Building License", lic.name, "status", "Expiring Soon")
            except Exception:
                frappe.db.rollback(save_point=_ROW_SAVEPOINT)
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=f"License expiry check failed for {lic.name}"[:140],
                )

        cursor = licenses[-1].name


def _raise_maintenance_alert(
    req_name: str,
    priority: str,
    elapsed_hours: float,
    threshold_hours: int,
    issue_type: str,
    status: str,
) -> None:
    """Insert an Operations Alert for an overdue Maintenance Request (idempotent).

    Mirrors the Salis ``_raise_alert`` pattern: existence-guarded so one Open
    alert per (Maintenance Request, day) is never duplicated across runs. Both
    the insert and the optional timeline comment are individually guarded so a
    failure rolls back and logs but never aborts the calling loop.
    """
    from frappe.utils import today

    alert_type = "Maintenance Overdue"  # [#ihzt5o]
    severity = "Critical" if priority == "Critical" else "Warning"
    message = (
        f"open_maintenance_escalation: Maintenance Request {req_name} "
        f"({issue_type}, status: {status}) is overdue. "
        f"Priority: {priority}, hours open: {elapsed_hours:.1f} "
        f"(threshold: {threshold_hours} hours)."
    )[:2000]

    # [#glisou]
    frappe.db.savepoint(_ALERT_SAVEPOINT)
    try:
        today_str = today()
        if frappe.db.exists(
            "Operations Alert",
            {
                "alert_type": alert_type,
                "status": "Open",
                "message": ["like", f"%{req_name}%"],
                "raised_on": ["between", [f"{today_str} 00:00:00", f"{today_str} 23:59:59"]],
            },
        ):
            return
    except Exception:
        frappe.db.rollback(save_point=_ALERT_SAVEPOINT)
        frappe.log_error(
            message=frappe.get_traceback(),
            title=f"Maintenance alert dedupe check failed ({req_name})"[:140],
        )
        return

    # [#rx9vmh] Insert via the shared helper (ignore_permissions + message clip +
    # rollback/log_error) — a maintenance alert carries no vehicle/driver. A failed/None
    # insert skips the timeline comment below, exactly as the old try/except return did.
    if insert_operations_alert(alert_type, severity, message) is None:
        return

    # [#q02x8v]
    frappe.db.savepoint(_ALERT_SAVEPOINT)
    try:
        frappe.get_doc("Maintenance Request", req_name).add_comment("Comment", message)
    except Exception:
        frappe.db.rollback(save_point=_ALERT_SAVEPOINT)
        frappe.log_error(
            message=frappe.get_traceback(),
            title=f"Maintenance alert comment failed for {req_name}"[:140],
        )


def open_maintenance_escalation() -> None:
    """Escalate overdue open Maintenance Requests.

    Checks open requests (docstatus != 2, status in ('Open', 'Assigned', 'In Progress', 'Reopened'))
    and logs escalations based on priority and elapsed time.
    Also inserts an Operations Alert for each overdue ticket (idempotent — one
    Open alert per request per day; see _raise_maintenance_alert).
    """
    from frappe.utils import now_datetime, get_datetime

    now = now_datetime()
    logger = frappe.logger()

    # [#6x8ro4]
    thresholds = {
        "Critical": 24,
        "High": 72,
        "Medium": 168,
        "Low": 336
    }

    # [#bz0n3e]
    start = 0
    batch_size = 500
    while True:
        open_requests = frappe.get_all(
            "Maintenance Request",
            filters={
                "docstatus": ["!=", 2],
                "status": ["in", ["Open", "Assigned", "In Progress", "Reopened"]]
            },
            fields=["name", "priority", "creation", "status", "issue_type"],
            limit_start=start,
            limit_page_length=batch_size,
        )
        if not open_requests:
            break

        for req in open_requests:
            frappe.db.savepoint(_ROW_SAVEPOINT)
            try:  # [#jrhqtd]
                priority = req.priority or "Medium"
                threshold_hours = thresholds.get(priority, 168)

                creation_dt = get_datetime(req.creation)
                elapsed_hours = (now - creation_dt).total_seconds() / 3600.0

                if elapsed_hours > threshold_hours:
                    logger.warning(
                        f"Maintenance Request {req.name} ({req.issue_type}, status: {req.status}) "
                        f"is overdue! Priority: {priority}, hours open: {elapsed_hours:.1f} (threshold: {threshold_hours} hours)."
                    )
                    _raise_maintenance_alert(
                        req_name=req.name,
                        priority=priority,
                        elapsed_hours=elapsed_hours,
                        threshold_hours=threshold_hours,
                        issue_type=req.issue_type or "",
                        status=req.status or "",
                    )
            except Exception:
                frappe.db.rollback(save_point=_ROW_SAVEPOINT)
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=f"Maintenance escalation failed for {req.name}"[:140],
                )
                continue

        start += batch_size
