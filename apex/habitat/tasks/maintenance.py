# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.utils import get_datetime, now_datetime, today

from apex.apex_core.utils.role_assignment import assign_role, reconcile_role_queue
from apex.habitat.doctype.building_license.building_license import derive_license_status

_ROW_SAVEPOINT = "maintenance_row"


def daily_building_license_expiry_check() -> None:
    today_str = today()

    cursor = ""
    batch_size = 500
    while True:
        licenses = frappe.get_all(
            "Building License",
            filters={
                "docstatus": 1,
                "status": ["!=", "Revoked"],
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
                status = derive_license_status(lic.expiry_date, lead_days, today_str)
                if lic.status != status:
                    frappe.db.set_value("Building License", lic.name, "status", status)
            except Exception:
                frappe.db.rollback(save_point=_ROW_SAVEPOINT)
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=f"License expiry check failed for {lic.name}"[:140],
                )

        cursor = licenses[-1].name


MAINTENANCE_ROLE = "Accommodation Manager"


def _queue_overdue_request(req_name, priority, elapsed_hours, threshold_hours, issue_type, status):
    message = (
        f"Maintenance Request {req_name} ({issue_type}, status: {status}) is overdue. "
        f"Priority: {priority}, hours open: {elapsed_hours:.1f} "
        f"(threshold: {threshold_hours} hours)."
    )[:2000]
    newly_assigned = assign_role(
        "Maintenance Request",
        req_name,
        MAINTENANCE_ROLE,
        description=message,
        priority="High" if priority in ("Critical", "High") else "Medium",
    )
    if not newly_assigned:
        return
    frappe.db.savepoint(_ROW_SAVEPOINT)
    try:
        frappe.get_doc("Maintenance Request", req_name).add_comment("Comment", message)
    except Exception:
        frappe.db.rollback(save_point=_ROW_SAVEPOINT)
        frappe.log_error(
            message=frappe.get_traceback(),
            title=f"Maintenance alert comment failed for {req_name}"[:140],
        )


def open_maintenance_escalation() -> None:
    now = now_datetime()
    logger = frappe.logger()

    thresholds = {
        "Critical": 24,
        "High": 72,
        "Medium": 168,
        "Low": 336
    }

    still_overdue: list[str] = []

    start = 0
    batch_size = 500
    while True:
        open_requests = frappe.get_all(
            "Maintenance Request",
            filters={
                "docstatus": ["!=", 2],
                "status": ["in", ["Open", "In Progress"]]
            },
            fields=["name", "priority", "creation", "status", "issue_type"],
            limit_start=start,
            limit_page_length=batch_size,
        )
        if not open_requests:
            break

        for req in open_requests:
            frappe.db.savepoint(_ROW_SAVEPOINT)
            try:
                priority = req.priority or "Medium"
                threshold_hours = thresholds.get(priority, 168)

                creation_dt = get_datetime(req.creation)
                elapsed_hours = (now - creation_dt).total_seconds() / 3600.0

                if elapsed_hours > threshold_hours:
                    logger.warning(
                        f"Maintenance Request {req.name} ({req.issue_type}, status: {req.status}) "
                        f"is overdue! Priority: {priority}, hours open: {elapsed_hours:.1f} (threshold: {threshold_hours} hours)."
                    )
                    _queue_overdue_request(
                        req_name=req.name,
                        priority=priority,
                        elapsed_hours=elapsed_hours,
                        threshold_hours=threshold_hours,
                        issue_type=req.issue_type or "",
                        status=req.status or "",
                    )
                    still_overdue.append(req.name)
            except Exception:
                frappe.db.rollback(save_point=_ROW_SAVEPOINT)
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=f"Maintenance escalation failed for {req.name}"[:140],
                )
                continue

        start += batch_size

    reconcile_role_queue("Maintenance Request", still_overdue)
