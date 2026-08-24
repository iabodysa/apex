# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.utils import date_diff, flt, getdate, today

from apex.apex_core.utils.company import display_currency

from apex.habitat.tasks.common import _notify_operational

_ROW_SAVEPOINT = "residency_row"


def lease_expiry_watchlist() -> None:
    today_str = today()

    cursor = ""
    batch_size = 500
    while True:
        leases = frappe.get_all(
            "Lease",
            filters={"docstatus": 1, "status": ["in", ["Approved", "Active"]],
                     "lease_end_date": ["is", "set"], "name": [">", cursor]},
            fields=["name", "lease_end_date"],
            order_by="name asc",
            limit_page_length=batch_size,
        )
        if not leases:
            break

        for lease in leases:
            frappe.db.savepoint(_ROW_SAVEPOINT)
            try:
                if date_diff(lease.lease_end_date, today_str) < 0:
                    frappe.db.set_value("Lease", lease.name, "status", "Expired")
            except Exception:
                frappe.db.rollback(save_point=_ROW_SAVEPOINT)
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=f"Lease expiry watchlist failed for {lease.name}"[:140],
                )

        cursor = leases[-1].name


def idle_resident_aging() -> None:
    today_str = today()
    start = 0
    batch_size = 500
    while True:
        reports = frappe.get_all(
            "Idle Resident Report",
            filters={"status": ["in", ["Open", "Acknowledged"]]},
            fields=["name", "reported_on", "assignment", "employee_name", "employee"],
            limit_start=start,
            limit_page_length=batch_size,
        )
        if not reports:
            break

        asgn_ids = {r.assignment for r in reports if r.assignment and r.reported_on}
        ledger_by_assignment: dict = {}
        if asgn_ids:
            for x in frappe.get_all(
                "Accommodation Ledger",
                filters={"assignment": ["in", list(asgn_ids)], "posting_date": ["<=", today_str]},
                fields=["assignment", "posting_date", "employee_daily_share"],
            ):
                ledger_by_assignment.setdefault(x.assignment, []).append(x)

        for r in reports:
            frappe.db.savepoint(_ROW_SAVEPOINT)
            try:
                days = date_diff(today_str, r.reported_on) if r.reported_on else 0
                cost = 0.0
                if r.assignment and r.reported_on:
                    reported_date = getdate(r.reported_on)
                    cost = flt(
                        sum(
                            flt(x.employee_daily_share)
                            for x in ledger_by_assignment.get(r.assignment, [])
                            if getdate(x.posting_date) >= reported_date
                        )
                    )
                frappe.db.set_value(
                    "Idle Resident Report", r.name,
                    {"days_idle": days, "estimated_cost_bleed": cost},
                    update_modified=False,
                )
                if days and days % 7 == 0:
                    worker = r.employee_name or r.employee
                    _notify_operational(
                        "Idle Resident Report", r.name,
                        f"idle_resident_aging: {worker} has now been a cost bleed for {days} days "
                        f"(estimated accommodation cost {cost} {display_currency()}).",
                    )
            except Exception:
                frappe.db.rollback(save_point=_ROW_SAVEPOINT)
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=f"Idle resident aging failed for {r.name}"[:140],
                )

        start += batch_size
