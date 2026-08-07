# Copyright (c) 2026, AFMCO and contributors
"""Scheduled tasks for the Salis fleet module (split by domain)."""

from __future__ import annotations

import frappe
from frappe.query_builder.functions import Coalesce, Sum

from apex.salis.tasks.common import (
    _reconcile_queue,
    _settings_int,
)

_ROW_SAVEPOINT = "salis_alerts_row"


def reconcile_operations_alerts() -> None:
    """Drain the Fleet Supervisor assignment queues whose underlying condition no
    longer holds, so queued work does not accumulate forever.

    This is the single reconcile point for the three DocTypes that more than one
    job (or none of its own) can queue — Salis Vehicle (idle watches + compliance
    watch), Salis Driver (attendance watch) and Fuel Quota (the monthly fuel
    reconciliation) — because reconcile_role_queue's contract needs the UNION of
    every condition per DocType, and a per-writer reconcile would close the other
    writers' work. Vehicle Suspension and Rental Office reconcile inside their
    sole writer jobs.

    A document stays queued while ANY of its writers' conditions holds:

    * **Salis Vehicle** — Active with no submitted Dispatch Trip
      (Dispatched/Completed) within ``idle_vehicle_days``, OR Active with a
      compliance row expired or expiring within ``alert_lead_days``.
    * **Salis Driver** — Active with no submitted Driver Attendance today.
    * **Fuel Quota** — the current-month Active quota is still breached
      (ledgered consumption above the quota plus margin).

    Idempotent and never aborts: each DocType's drain runs in its own
    try/except with rollback-before-log.
    """
    from frappe.utils import add_days, today

    today_str = today()
    logger = frappe.logger()

    idle_days = _settings_int("idle_vehicle_days", 7)
    lead_days = _settings_int("alert_lead_days", 30)
    idle_cutoff = add_days(today_str, -idle_days)

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

    from apex.salis.fuel_engine import _period_month, get_overage_margin

    breached_quotas: set[str] = set()
    overage_margin = get_overage_margin()
    period_month = _period_month(today_str)
    Q = frappe.qb.DocType("Fuel Quota")
    L = frappe.qb.DocType("Fuel Consumption Ledger")
    for r in (
        frappe.qb.from_(Q)
        .left_join(L)
        .on((L.vehicle == Q.vehicle) & (L.period_month == Q.period_month))
        .select(
            Q.name.as_("quota_name"),
            Q.monthly_litres.as_("quota"),
            Coalesce(Sum(L.litres), 0).as_("consumed"),
        )
        .where(Q.docstatus == 1)
        .where(Q.status == "Active")
        .where(Q.period_month == period_month)
        .where(Q.vehicle.isnotnull())
        .groupby(Q.name, Q.monthly_litres)
    ).run(as_dict=True):
        quota = float(r["quota"] or 0)
        consumed = float(r["consumed"] or 0)
        if quota > 0 and consumed > quota * (1 + overage_margin):
            breached_quotas.add(r["quota_name"])

    active_vehicles = set(
        frappe.get_all("Salis Vehicle", filters={"status": "Active"}, pluck="name")
    )
    vehicle_keep = (active_vehicles - vehicles_with_recent_trip) | (
        vehicles_with_open_compliance & active_vehicles
    )

    active_drivers = set(
        frappe.get_all("Salis Driver", filters={"status": "Active"}, pluck="name")
    )
    attended_today = {
        r["driver"]
        for r in frappe.get_all(
            "Driver Attendance",
            filters={"attendance_date": today_str, "docstatus": 1},
            fields=["driver"],
        )
        if r["driver"]
    }
    driver_keep = active_drivers - attended_today

    drained = 0
    for doctype, keep in (
        ("Salis Vehicle", vehicle_keep),
        ("Salis Driver", driver_keep),
        ("Fuel Quota", breached_quotas),
    ):
        frappe.db.savepoint(_ROW_SAVEPOINT)
        try:
            drained += _reconcile_queue(doctype, keep)
        except Exception:
            frappe.db.rollback(save_point=_ROW_SAVEPOINT)
            frappe.log_error(
                message=frappe.get_traceback(),
                title=f"Queue reconciliation failed for {doctype}"[:140],
            )

    logger.info(
        f"reconcile_operations_alerts: drained {drained} assignment(s) whose "
        f"condition has cleared."
    )
