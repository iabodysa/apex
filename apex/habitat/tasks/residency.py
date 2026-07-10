# Copyright (c) 2026, AFMCO and contributors
"""Scheduled tasks for the Habitat module (split by domain)."""

from __future__ import annotations

import frappe

from apex.habitat.tasks.common import _notify_operational


def lease_expiry_watchlist() -> None:
    """Alert on leases expiring within the configured lead days.

    Queries Accommodation Lease (submitted, live status) directly —
    the authoritative source for lease dates. A live lease is one the
    approval workflow has submitted (status=Approved) or that has been
    moved into its post-approval lifecycle (status=Active); both are
    in force and watchlisted.
    Sets lease status = Expired when lease_end_date has passed.
    """
    from frappe.utils import date_diff, today

    today_str = today()
    logger = frappe.logger()
    lease_lead = frappe.db.get_single_value("Habitat Settings", "lease_expiry_days_before") or 90

    start = 0
    batch_size = 500
    while True:
        leases = frappe.get_all(
            "Lease",
            filters={"docstatus": 1, "status": ["in", ["Approved", "Active"]],
                     "lease_end_date": ["is", "set"]},
            fields=["name", "building", "lease_end_date"],
            limit_start=start,
            limit_page_length=batch_size,
        )
        if not leases:
            break

        for lease in leases:
            try:
                days = date_diff(lease.lease_end_date, today_str)
                if days < 0:
                    frappe.db.set_value("Lease", lease.name, "status", "Expired")
                    msg = (
                        f"lease_expiry_watchlist: lease {lease.name} "
                        f"(building {lease.building}) expired {abs(days)} days ago."
                    )
                    logger.warning(msg)
                    _notify_operational("Lease", lease.name, msg)
                elif 0 <= days <= lease_lead:
                    msg = (
                        f"lease_expiry_watchlist: lease {lease.name} "
                        f"(building {lease.building}) expires in {days} days ({lease.lease_end_date})."
                    )
                    logger.warning(msg)
                    _notify_operational("Lease", lease.name, msg)
            except Exception:
                frappe.db.rollback()
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=f"Lease expiry watchlist failed for {lease.name}"[:140],
                )

        start += batch_size


def temporary_stay_checkout_watchlist() -> None:
    """Flag temporary stays whose expected check-out date has arrived or passed
    while the worker is still checked in.

    Active stay = submitted Accommodation Assignment with no check_out_date. For
    each temporary one, compare today to expected_checkout_date; post a timeline
    comment (gated by Enable Operational Notifications) on overdue stays, and on
    those due within the Temporary Stay Lead Days. Mirrors lease_expiry_watchlist:
    paginated 500/batch, per-row error isolation. Sets no state field.
    """
    from frappe.utils import date_diff, today

    today_str = today()
    logger = frappe.logger()
    start = 0
    batch_size = 500
    while True:
        stays = frappe.get_all(
            "Housing Assignment",
            filters={
                "stay_type": "Temporary",
                "docstatus": 1,
                "check_out_date": ["is", "not set"],
                "expected_checkout_date": ["is", "set"],
            },
            fields=["name", "employee", "employee_name", "expected_checkout_date"],
            limit_start=start,
            limit_page_length=batch_size,
        )
        if not stays:
            break

        lead = frappe.db.get_single_value("Habitat Settings", "temporary_stay_days_before") or 2
        for s in stays:
            try:
                days = date_diff(s.expected_checkout_date, today_str)
                worker = s.employee_name or s.employee
                if days < 0:
                    msg = (f"temporary_stay_checkout_watchlist: {worker} is overdue — expected check-out was "
                           f"{s.expected_checkout_date} ({abs(days)} days ago) and the worker is still checked in.")
                    logger.warning(msg)
                    _notify_operational("Housing Assignment", s.name, msg)
                elif 0 <= days <= lead:
                    msg = (f"temporary_stay_checkout_watchlist: {worker}'s temporary stay ends on "
                           f"{s.expected_checkout_date} (in {days} days). Please arrange check-out.")
                    logger.warning(msg)
                    _notify_operational("Housing Assignment", s.name, msg)
            except Exception:
                frappe.db.rollback()
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=f"Temporary stay watchlist failed for {s.name}"[:140],
                )

        start += batch_size


def idle_resident_aging() -> None:
    """Accrue days-idle and the estimated accommodation cost bleed for every open
    Idle Resident Report.

    days_idle = today - reported_on. Cost bleed = sum of the per-resident daily
    share already posted to the Accommodation Ledger (Operational Memo) for the
    linked assignment over the idle window — no GL, reuses existing memo data.
    Paginated 500/batch with per-row error isolation; posts a timeline note every
    7 idle days when operational notifications are enabled.
    """
    from frappe.utils import date_diff, flt, getdate, today

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

        # Bulk-prefetch every ledger memo (assignment, posting_date <= today) for the
        # batch's assignments in one query, grouped by assignment, instead of one
        # get_all per report (N+1). The per-report reported_on..today window is then
        # applied in memory below, so each report's cost bleed is unchanged.
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
                        f"(estimated accommodation cost {cost} SAR).",
                    )
            except Exception:
                frappe.db.rollback()
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=f"Idle resident aging failed for {r.name}"[:140],
                )

        start += batch_size
