# Copyright (c) 2026, AFMCO and contributors
"""Scheduled tasks for the Salis fleet module (split by domain)."""

from __future__ import annotations

import frappe
from frappe import _

from apex_habitat.salis.tasks.common import (
    ALERT_DOCTYPE,
    BATCH_SIZE,
    _publish_operations_alert,
    _resolve_alert,
    _settings_int,
    _vehicle_project,
)


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

    from apex_habitat.apex_core.utils.email_gate import email_enabled

    logger = frappe.logger()

    # Master email kill-switch (default OFF): without it the daily send floods
    # OutgoingEmailError on a site with no outgoing Email Account configured.
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
        try:
            if not frappe.db.get_value("User", supervisor, "enabled"):
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
            frappe.db.rollback()
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

    # [#dh8hm0]
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

    # [#e2kiah]
    vehicles_with_recent_trip = {
        r["vehicle"]
        for r in frappe.db.sql(
            """
            SELECT vehicle FROM `tabDispatch Trip`
            WHERE docstatus = 1 AND status IN ('Dispatched', 'Completed')
              AND trip_date >= %(cutoff)s AND vehicle IS NOT NULL
            GROUP BY vehicle
            """,
            {"cutoff": idle_cutoff},
            as_dict=True,
        )
    }

    # [#ckt0ba]
    horizon = add_days(today_str, lead_days)
    vehicles_with_open_compliance = {
        r["parent"]
        for r in frappe.db.sql(
            """
            SELECT DISTINCT parent FROM `tabSalis Vehicle Compliance`
            WHERE expiry_date IS NOT NULL AND expiry_date <= %(horizon)s
            """,
            {"horizon": horizon},
            as_dict=True,
        )
    }

    # [#2yh1kv]
    overdue_request_vehicles = set()
    overdue_request_drivers = set()
    for r in frappe.db.sql(
        """
        SELECT vehicle, driver FROM `tabFuel Request`
        WHERE docstatus = 1 AND status = 'Pending' AND request_date < %(cutoff)s
        """,
        {"cutoff": pending_cutoff},
        as_dict=True,
    ):
        if r["vehicle"]:
            overdue_request_vehicles.add(r["vehicle"])
        if r["driver"]:
            overdue_request_drivers.add(r["driver"])

    # [#4oiqbl]
    excessive_topup_vehicles = {
        r["vehicle"]
        for r in frappe.db.sql(
            """
            SELECT DISTINCT vehicle FROM `tabFuel Request`
            WHERE request_type = 'Top-up' AND is_temporary = 1 AND reverted = 0
              AND docstatus = 1 AND status IN ('Approved', 'Done')
              AND revert_due_date < %(today)s AND vehicle IS NOT NULL
            """,
            {"today": today_str},
            as_dict=True,
        )
    }
    from apex_habitat.salis.fuel_engine import _period_month, get_overage_margin

    overage_margin = get_overage_margin()
    period_month = _period_month(today_str)
    for r in frappe.db.sql(
        """
        SELECT q.vehicle AS vehicle, q.monthly_litres AS quota,
               COALESCE(SUM(l.litres), 0) AS consumed
        FROM `tabFuel Quota` q
        LEFT JOIN `tabFuel Consumption Ledger` l
          ON l.vehicle = q.vehicle AND l.period_month = q.period_month
        WHERE q.docstatus = 1 AND q.status = 'Active'
          AND q.period_month = %(period)s AND q.vehicle IS NOT NULL
        GROUP BY q.name, q.vehicle, q.monthly_litres
        """,
        {"period": period_month},
        as_dict=True,
    ):
        quota = float(r["quota"] or 0)
        consumed = float(r["consumed"] or 0)
        if quota > 0 and consumed > quota * (1 + overage_margin):
            excessive_topup_vehicles.add(r["vehicle"])

    def _vehicle_active(vehicle: str | None) -> bool:
        return bool(vehicle) and frappe.db.get_value("Salis Vehicle", vehicle, "status") == "Active"

    def _driver_active(driver: str | None) -> bool:
        return bool(driver) and frappe.db.get_value("Salis Driver", driver, "status") == "Active"

    # [#dkxfl4]
    resolved_projects: set[str | None] = set()
    start = 0
    while True:
        alerts = frappe.get_all(
            ALERT_DOCTYPE,
            filters={"status": ["in", ["Open", "Acknowledged"]]},
            fields=["name", "alert_type", "vehicle", "driver", "raised_on"],
            limit_start=start,
            limit_page_length=BATCH_SIZE,
        )
        if not alerts:
            break

        for a in alerts:
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
                    # [#1hftuh]
                    if a.vehicle and a.vehicle not in excessive_topup_vehicles:
                        clear, reason = True, "no fuel overage or unreverted top-up remains for the vehicle"

                if clear and _resolve_alert(a.name, reason):
                    resolved_count += 1
                    resolved_projects.add(_vehicle_project(a.vehicle))
            except Exception:
                frappe.db.rollback()
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=f"Alert reconciliation failed for {a.name}"[:140],
                )

        start += BATCH_SIZE

    # Push the operations board to refetch once per project whose alert(s) cleared,
    # so a resolved alert disappears without a manual Refresh.
    for project in resolved_projects:
        _publish_operations_alert(project)

    logger.info(
        f"reconcile_operations_alerts: resolved {resolved_count} alert(s) whose "
        f"condition has cleared."
    )
