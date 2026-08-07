# Copyright (c) 2026, AFMCO and contributors
"""Scheduled tasks for the Salis fleet module (split by domain)."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.query_builder.functions import Coalesce, Sum

from apex.salis.tasks.common import (
    ALERT_DOCTYPE,
    BATCH_SIZE,
    _publish_operations_alert,
    _resolve_alert,
    _settings_int,
    _vehicle_project,
)

_ROW_SAVEPOINT = "salis_alerts_row"


def daily_open_alerts_digest() -> None:
    """Email each Fleet Supervisor a daily roll-up of their open Operations Alerts.

    Complements the per-alert Critical notification (fires once on raise) with a
    standing summary: every Open/Acknowledged alert, grouped by the denormalised
    ``responsible_supervisor`` (the owning supervisor of the alert's project). Each
    supervisor receives only their own bucket, so the digest respects the same
    project boundary as the desk without re-deriving scope here.

    Alerts with no ``responsible_supervisor`` (e.g. driver-only alerts that resolve no
    project) have no owning supervisor and are skipped — oversight roles already
    see every alert. Per-supervisor delivery is isolated (rollback before log) so
    one bad recipient never aborts the rest. Idempotent enough for daily cadence:
    re-running re-sends the current snapshot, it never mutates state.
    """
    from collections import defaultdict

    from frappe.utils import escape_html, get_url_to_list

    from apex.apex_core.utils.email_gate import email_enabled, mailable

    logger = frappe.logger()

    if not email_enabled():
        logger.info("daily_open_alerts_digest: email disabled (Habitat Settings); skipped.")
        return

    by_supervisor: dict[str, list] = defaultdict(list)
    start = 0
    while True:
        alerts = frappe.get_all(
            ALERT_DOCTYPE,
            filters={
                "status": ["in", ["Open", "Acknowledged"]],
                "responsible_supervisor": ["is", "set"],
            },
            fields=["name", "alert_type", "severity", "vehicle", "driver",
                    "message", "responsible_supervisor"],
            order_by="severity asc, raised_on asc",
            limit_start=start,
            limit_page_length=BATCH_SIZE,
        )
        if not alerts:
            break
        for a in alerts:
            by_supervisor[a.responsible_supervisor].append(a)
        start += BATCH_SIZE

    if not by_supervisor:
        logger.info("daily_open_alerts_digest: no open alerts with an owning supervisor.")
        return

    list_url = get_url_to_list(ALERT_DOCTYPE)
    severities = ("Critical", "Warning", "Info")
    sent = 0
    for supervisor, rows in by_supervisor.items():
        frappe.db.savepoint(_ROW_SAVEPOINT)
        try:
            if not mailable([supervisor]):
                continue
            counts = {s: sum(1 for r in rows if r.severity == s) for s in severities}
            summary = ", ".join(
                _("{0}: {1}").format(_(s), counts[s]) for s in severities if counts[s]
            )
            items = "".join(
                "<li>[{severity}] {atype} — {target}: {msg}</li>".format(
                    severity=escape_html(_(r.severity)),
                    atype=escape_html(_(r.alert_type)),
                    target=escape_html(r.vehicle or r.driver or "—"),
                    msg=escape_html((r.message or "")[:200]),
                )
                for r in rows
            )
            message = "{intro} ({summary}).<br><ul>{items}</ul><br><a href='{url}'>{cta}</a>".format(
                intro=_("You have {0} open operations alert(s)").format(len(rows)),
                summary=summary,
                items=items,
                url=list_url,
                cta=_("Open the operations alert list"),
            )
            frappe.sendmail(
                recipients=[supervisor],
                subject=_("Daily Open Operations Alerts: {0}").format(len(rows)),
                message=message,
            )
            sent += 1
        except Exception:
            frappe.db.rollback(save_point=_ROW_SAVEPOINT)
            frappe.log_error(
                message=frappe.get_traceback(),
                title=f"Open-alerts digest failed for {supervisor}"[:140],
            )

    logger.info(f"daily_open_alerts_digest: sent {sent} supervisor digest(s).")


def reconcile_operations_alerts() -> None:
    """Auto-resolve open/acknowledged Operations Alerts whose underlying condition
    no longer holds, so alerts do not accumulate forever.

    Nothing previously closed alerts (License Expiry / Idle Vehicle / overdue
    request / attendance-gap rows piled up indefinitely). This daily pass
    re-evaluates the live condition that originally raised each open alert and
    flips it to ``Resolved`` once cleared:

    * **Idle Vehicle** — the vehicle now has a submitted Dispatch Trip
      (Dispatched/Completed) within ``idle_vehicle_days``, or is no longer Active.
    * **License Expiry** — (vehicle) no Salis Vehicle Compliance row is expired or
      within ``alert_lead_days``; (driver) the driver's licence is beyond the lead
      window, or the driver is no longer Active.
    * **Forgotten Request** — no submitted Fuel Request remains Pending past
      ``fuel_pending_max_days`` for the alert's vehicle/driver.
    * **Supervisor Delay** — the driver has a submitted Driver Attendance for the
      day the alert was raised, or is no longer Active.
    * **Excessive Topup** — neither source still breaches for the vehicle: no
      unreverted temporary top-up remains past its revert-due date AND current-
      month ledgered consumption is back within the active quota (+ margin). The
      overdue-top-up variant is also resolved immediately on the revert event
      (``Fuel Request.on_update_after_submit``); this pass is the catch-up.

    Idempotent (already-Resolved rows are skipped by the status filter; a re-run
    resolves nothing new once conditions are stable) and never aborts: each alert
    is handled in its own try/except with rollback-before-log.
    """
    from frappe.utils import add_days, getdate, today

    today_str = today()
    today_date = getdate(today_str)
    logger = frappe.logger()
    resolved_count = 0

    idle_days = _settings_int("idle_vehicle_days", 7)
    lead_days = _settings_int("alert_lead_days", 30)
    license_lead = max(
        _settings_int("license_alert_lead_days", 30),
        _settings_int("alert_lead_days", 7),
        30,
    )
    pending_max_days = _settings_int("fuel_pending_max_days", 2)
    idle_cutoff = add_days(today_str, -idle_days)
    pending_cutoff = add_days(today_str, -pending_max_days)

    DT = frappe.qb.DocType("Dispatch Trip")
    vehicles_with_recent_trip = {
        r["vehicle"]
        for r in (
            frappe.qb.from_(DT)
            .select(DT.vehicle)
            .where(DT.docstatus == 1)
            .where(DT.status.isin(["Dispatched", "Completed"]))
            .where(DT.trip_date >= idle_cutoff)
            .where(DT.vehicle.isnotnull())
            .groupby(DT.vehicle)
        ).run(as_dict=True)
    }

    horizon = add_days(today_str, lead_days)
    SVC = frappe.qb.DocType("Salis Vehicle Compliance")
    vehicles_with_open_compliance = {
        r["parent"]
        for r in (
            frappe.qb.from_(SVC)
            .select(SVC.parent)
            .distinct()
            .where(SVC.expiry_date.isnotnull())
            .where(SVC.expiry_date <= horizon)
        ).run(as_dict=True)
    }

    FR = frappe.qb.DocType("Fuel Request")
    overdue_request_vehicles = set()
    overdue_request_drivers = set()
    for r in (
        frappe.qb.from_(FR)
        .select(FR.vehicle, FR.driver)
        .where(FR.docstatus == 1)
        .where(FR.status == "Pending")
        .where(FR.request_date < pending_cutoff)
    ).run(as_dict=True):
        if r["vehicle"]:
            overdue_request_vehicles.add(r["vehicle"])
        if r["driver"]:
            overdue_request_drivers.add(r["driver"])

    excessive_topup_vehicles = {
        r["vehicle"]
        for r in (
            frappe.qb.from_(FR)
            .select(FR.vehicle)
            .distinct()
            .where(FR.request_type == "Top-up")
            .where(FR.is_temporary == 1)
            .where(FR.reverted == 0)
            .where(FR.docstatus == 1)
            .where(FR.status.isin(["Approved", "Done"]))
            .where(FR.revert_due_date < today_str)
            .where(FR.vehicle.isnotnull())
        ).run(as_dict=True)
    }
    from apex.salis.fuel_engine import _period_month, get_overage_margin

    overage_margin = get_overage_margin()
    period_month = _period_month(today_str)
    Q = frappe.qb.DocType("Fuel Quota")
    L = frappe.qb.DocType("Fuel Consumption Ledger")
    for r in (
        frappe.qb.from_(Q)
        .left_join(L)
        .on((L.vehicle == Q.vehicle) & (L.period_month == Q.period_month))
        .select(
            Q.vehicle.as_("vehicle"),
            Q.monthly_litres.as_("quota"),
            Coalesce(Sum(L.litres), 0).as_("consumed"),
        )
        .where(Q.docstatus == 1)
        .where(Q.status == "Active")
        .where(Q.period_month == period_month)
        .where(Q.vehicle.isnotnull())
        .groupby(Q.name, Q.vehicle, Q.monthly_litres)
    ).run(as_dict=True):
        quota = float(r["quota"] or 0)
        consumed = float(r["consumed"] or 0)
        if quota > 0 and consumed > quota * (1 + overage_margin):
            excessive_topup_vehicles.add(r["vehicle"])

    def _vehicle_active(vehicle: str | None) -> bool:
        return bool(vehicle) and frappe.db.get_value("Salis Vehicle", vehicle, "status") == "Active"

    def _driver_active(driver: str | None) -> bool:
        return bool(driver) and frappe.db.get_value("Salis Driver", driver, "status") == "Active"

    resolved_projects: set[str | None] = set()
    cursor = ""
    while True:
        alerts = frappe.get_all(
            ALERT_DOCTYPE,
            filters={"status": ["in", ["Open", "Acknowledged"]], "name": [">", cursor]},
            fields=["name", "alert_type", "vehicle", "driver", "raised_on"],
            order_by="name asc",
            limit_page_length=BATCH_SIZE,
        )
        if not alerts:
            break

        for a in alerts:
            frappe.db.savepoint(_ROW_SAVEPOINT)
            try:
                clear = False
                reason = ""
                atype = a.alert_type

                if atype == "Idle Vehicle":
                    if not _vehicle_active(a.vehicle):
                        clear, reason = True, "vehicle is no longer Active"
                    elif a.vehicle in vehicles_with_recent_trip:
                        clear, reason = True, "vehicle has a recent dispatch trip"

                elif atype == "License Expiry":
                    if a.vehicle:
                        if not _vehicle_active(a.vehicle):
                            clear, reason = True, "vehicle is no longer Active"
                        elif a.vehicle not in vehicles_with_open_compliance:
                            clear, reason = True, "vehicle compliance is no longer expiring"
                    elif a.driver:
                        if not _driver_active(a.driver):
                            clear, reason = True, "driver is no longer Active"
                        else:
                            expiry = frappe.db.get_value("Salis Driver", a.driver, "license_expiry")
                            if expiry and getdate(expiry) > add_days(today_date, license_lead):
                                clear, reason = True, "driver licence renewed"

                elif atype == "Forgotten Request":
                    if a.vehicle and a.vehicle not in overdue_request_vehicles:
                        clear, reason = True, "no fuel request remains overdue for the vehicle"
                    elif a.driver and not a.vehicle and a.driver not in overdue_request_drivers:
                        clear, reason = True, "no fuel request remains overdue for the driver"

                elif atype == "Supervisor Delay":
                    if not _driver_active(a.driver):
                        clear, reason = True, "driver is no longer Active"
                    elif a.driver:
                        raised_day = str(a.raised_on)[:10] if a.raised_on else today_str
                        if frappe.db.exists(
                            "Driver Attendance",
                            {"driver": a.driver, "attendance_date": raised_day, "docstatus": 1},
                        ):
                            clear, reason = True, "attendance has since been recorded"

                elif atype == "Excessive Topup":
                    if a.vehicle and a.vehicle not in excessive_topup_vehicles:
                        clear, reason = True, "no fuel overage or unreverted top-up remains for the vehicle"

                if clear and _resolve_alert(a.name, reason):
                    resolved_count += 1
                    resolved_projects.add(_vehicle_project(a.vehicle))
            except Exception:
                frappe.db.rollback(save_point=_ROW_SAVEPOINT)
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=f"Alert reconciliation failed for {a.name}"[:140],
                )

        cursor = alerts[-1].name

    for project in resolved_projects:
        _publish_operations_alert(project)

    logger.info(
        f"reconcile_operations_alerts: resolved {resolved_count} alert(s) whose "
        f"condition has cleared."
    )
