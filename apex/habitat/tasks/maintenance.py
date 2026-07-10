# Copyright (c) 2026, AFMCO and contributors
"""Scheduled tasks for the Habitat module (split by domain)."""

from __future__ import annotations

import frappe

from apex.habitat.tasks.common import _notify_operational


def daily_building_license_expiry_check() -> None:
    """Warn when Building License documents are approaching or past expiry.

    Updates status of Building License records:
    - Expired: if today is past or equal to expiry_date.
    - Expiring Soon: if today is within renewal_lead_days (default 60) of expiry_date.
    """
    from frappe.utils import today, date_diff

    today_str = today()
    logger = frappe.logger()

    # [#bz69zh]
    start = 0
    batch_size = 500
    while True:
        licenses = frappe.get_all(
            "Building License",
            filters={
                "docstatus": 1,
                "status": ["in", ["Active", "Expiring Soon"]]
            },
            fields=["name", "expiry_date", "renewal_lead_days", "status", "license_number", "license_type"],
            limit_start=start,
            limit_page_length=batch_size,
        )
        if not licenses:
            break

        default_lead = frappe.db.get_single_value("Habitat Settings", "license_expiry_days_before") or 60
        for lic in licenses:
            expiry_date = lic.expiry_date
            if not expiry_date:
                continue

            try:
                lead_days = lic.renewal_lead_days if lic.renewal_lead_days is not None else default_lead
                days_to_expiry = date_diff(expiry_date, today_str)

                if days_to_expiry <= 0:
                    if lic.status != "Expired":
                        frappe.db.set_value("Building License", lic.name, "status", "Expired")
                        msg = f"Building License {lic.name} ({lic.license_type} {lic.license_number}) has expired on {expiry_date}."
                        logger.warning(msg)
                        _notify_operational("Building License", lic.name, msg)
                elif days_to_expiry <= lead_days:
                    if lic.status != "Expiring Soon":
                        frappe.db.set_value("Building License", lic.name, "status", "Expiring Soon")
                        msg = f"Building License {lic.name} ({lic.license_type} {lic.license_number}) is expiring soon on {expiry_date} ({days_to_expiry} days remaining)."
                        logger.warning(msg)
                        _notify_operational("Building License", lic.name, msg)
            except Exception:
                frappe.db.rollback()  # [#7kjob3]
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=f"License expiry check failed for {lic.name}"[:140],
                )

        start += batch_size


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
    from frappe.utils import now_datetime, today

    alert_type = "Maintenance Overdue"  # [#ihzt5o]
    severity = "Critical" if priority == "Critical" else "Warning"
    message = (
        f"open_maintenance_escalation: Maintenance Request {req_name} "
        f"({issue_type}, status: {status}) is overdue. "
        f"Priority: {priority}, hours open: {elapsed_hours:.1f} "
        f"(threshold: {threshold_hours} hours)."
    )[:2000]

    # [#glisou]
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
        frappe.db.rollback()
        frappe.log_error(
            message=frappe.get_traceback(),
            title=f"Maintenance alert dedupe check failed ({req_name})"[:140],
        )
        return

    # [#rx9vmh]
    try:
        frappe.get_doc(
            {
                "doctype": "Operations Alert",
                "alert_type": alert_type,
                "severity": severity,
                "status": "Open",
                "raised_on": now_datetime(),
                "message": message,
            }
        ).insert(ignore_permissions=True)  # audit-ok — scheduler-run escalation, no user session
    except Exception:
        frappe.db.rollback()
        frappe.log_error(
            message=frappe.get_traceback(),
            title=f"Maintenance alert insert failed ({req_name})"[:140],
        )
        return

    # [#q02x8v]
    try:
        frappe.get_doc("Maintenance Request", req_name).add_comment("Comment", message)
    except Exception:
        frappe.db.rollback()
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
                frappe.db.rollback()
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=f"Maintenance escalation failed for {req.name}"[:140],
                )
                continue

        start += batch_size
