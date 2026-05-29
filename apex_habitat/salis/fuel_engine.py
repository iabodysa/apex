# Copyright (c) 2026, AFMCO and contributors
# For license information, please see license.txt

"""Fuel engine for the Salis Movement module.

Background engine that mirrors the Habitat no-GL, system-written ledger pattern
(``apex_habitat.habitat.doctype.accommodation_ledger``) and the batch/idempotent
scheduled-job style in ``apex_habitat.habitat.tasks``.

Two scheduled jobs:

* ``accrue_fuel_consumption`` (daily) — accrues a Fuel Consumption Ledger row for
  each recent Fuel Daily Log and each Done Fuel Request not yet ledgered.
  Idempotent on ``(source_type, source_name)``.
* ``monthly_fuel_reconciliation`` (monthly) — for each active Fuel Quota of the
  period, sums ledgered consumption for that vehicle+period against the quota's
  monthly litres; if consumption exceeds the quota beyond a tolerance margin it
  raises an "Excessive Topup" Operations Alert referencing the vehicle.
  Idempotent per vehicle+period+month.

No GL is written. The Operations Alert insert is done directly here (querying the
DocType) rather than importing ``salis.tasks`` to avoid coupling.
"""

from __future__ import annotations

import frappe

LEDGER_DOCTYPE = "Fuel Consumption Ledger"
ALERT_DOCTYPE = "Operations Alert"
BATCH_SIZE = 500

# Consumption is flagged only when it exceeds the quota by more than this
# fraction, to avoid alerting on rounding/measurement noise.
OVERAGE_MARGIN = 0.05


def _period_month(date_value) -> str:
    """Return the YYYY-MM period string for a date/datetime value."""
    return str(date_value)[:7]


def _ledger_exists(source_type: str, source_name: str) -> bool:
    """True if a ledger row already exists for this source (idempotency key)."""
    return bool(
        frappe.db.exists(
            LEDGER_DOCTYPE,
            {"source_type": source_type, "source_name": source_name},
        )
    )


def _company_for_vehicle(vehicle: str | None) -> str | None:
    """Resolve the owning company for a ledger row: the vehicle's own company,
    else the Salis Settings default. Reference only - carried for reporting
    grouping; the ledger posts no GL."""
    company = None
    if vehicle:
        company = frappe.db.get_value("Salis Vehicle", vehicle, "company")
    if not company:
        from apex_habitat.apex_core.doctype.salis_settings.salis_settings import (
            get_default_company,
        )

        company = get_default_company()
    return company or None


def _insert_ledger_row(
    vehicle: str,
    driver: str | None,
    period_month: str,
    litres: float,
    amount: float,
    source_type: str,
    source_name: str,
    logged_at,
) -> None:
    """Insert one Fuel Consumption Ledger row (system-written, no GL).

    Source traceability: ``source_type`` is the originating DocType name
    ("Fuel Daily Log" / "Fuel Request"), so ``source_doctype`` mirrors it and
    ``source_name`` points to the originating record.
    """
    frappe.get_doc(
        {
            "doctype": LEDGER_DOCTYPE,
            "vehicle": vehicle,
            "driver": driver,
            "company": _company_for_vehicle(vehicle),
            "period_month": period_month,
            "litres": litres,
            "amount": amount,
            "source_type": source_type,
            "source_doctype": source_type,
            "source_name": source_name,
            "logged_at": logged_at,
        }
    ).insert(ignore_permissions=True)  # audit-ok


# ---------------------------------------------------------------------------
# Daily accrual
# ---------------------------------------------------------------------------


def accrue_fuel_consumption() -> None:
    """Accrue Fuel Consumption Ledger rows for recent fuel activity.

    Sources:

    * Fuel Daily Log rows logged yesterday or today.
    * Fuel Requests in ``Done`` status (submitted) logged yesterday or today.

    Idempotent on ``(source_type, source_name)``: a source already ledgered is
    skipped. Per-row try/except isolates failures; no commit inside the loops.
    """
    from frappe.utils import add_days, flt, now_datetime, today

    today_str = today()
    yesterday_str = add_days(today_str, -1)
    logger = frappe.logger()

    # --- Fuel Daily Log ------------------------------------------------------
    start = 0
    while True:
        logs = frappe.get_all(
            "Fuel Daily Log",
            filters={"log_date": ["between", [yesterday_str, today_str]]},
            fields=["name", "vehicle", "driver", "log_date", "litres", "amount"],
            limit_start=start,
            limit_page_length=BATCH_SIZE,
        )
        if not logs:
            break

        for log in logs:
            try:
                if not log.vehicle:
                    continue
                if _ledger_exists("Fuel Daily Log", log.name):
                    continue
                _insert_ledger_row(
                    vehicle=log.vehicle,
                    driver=log.driver,
                    period_month=_period_month(log.log_date),
                    litres=flt(log.litres),
                    amount=flt(log.amount),
                    source_type="Fuel Daily Log",
                    source_name=log.name,
                    logged_at=now_datetime(),
                )
            except Exception:
                frappe.db.rollback()
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=f"Fuel accrual failed for Daily Log {log.name}"[:140],
                )

        start += BATCH_SIZE

    # --- Done Fuel Requests --------------------------------------------------
    start = 0
    while True:
        requests = frappe.get_all(
            "Fuel Request",
            filters={
                "docstatus": 1,
                "status": "Done",
                "request_date": ["between", [yesterday_str, today_str]],
            },
            fields=["name", "vehicle", "driver", "request_date", "requested_litres", "amount"],
            limit_start=start,
            limit_page_length=BATCH_SIZE,
        )
        if not requests:
            break

        for req in requests:
            try:
                if not req.vehicle:
                    continue
                if _ledger_exists("Fuel Request", req.name):
                    continue
                _insert_ledger_row(
                    vehicle=req.vehicle,
                    driver=req.driver,
                    period_month=_period_month(req.request_date),
                    litres=flt(req.requested_litres),
                    amount=flt(req.amount),
                    source_type="Fuel Request",
                    source_name=req.name,
                    logged_at=now_datetime(),
                )
            except Exception:
                frappe.db.rollback()
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=f"Fuel accrual failed for Request {req.name}"[:140],
                )

        start += BATCH_SIZE

    logger.info("accrue_fuel_consumption: fuel consumption ledger updated.")


# ---------------------------------------------------------------------------
# Monthly reconciliation
# ---------------------------------------------------------------------------


def _alert_already_raised(vehicle: str, period_month: str) -> bool:
    """True if an Excessive Topup alert was already raised for this vehicle in the
    month of ``period_month``. Idempotency key = (alert_type, vehicle, raised_on
    within that month). The previous implementation also matched the period inside
    the (translated) message text, which was fragile; the raised-on month window
    plus vehicle already identifies the alert uniquely for a given period.
    """
    from frappe.utils import get_first_day, get_last_day, getdate

    try:
        month_anchor = getdate(period_month + "-01")
    except Exception:
        return False

    start = f"{get_first_day(month_anchor)} 00:00:00"
    end = f"{get_last_day(month_anchor)} 23:59:59"
    return bool(
        frappe.db.exists(
            ALERT_DOCTYPE,
            {
                "alert_type": "Excessive Topup",
                "vehicle": vehicle,
                "raised_on": ["between", [start, end]],
            },
        )
    )


def monthly_fuel_reconciliation() -> None:
    """Reconcile each active Fuel Quota's allocation against ledgered consumption.

    For the current period (this month, YYYY-MM), every active Fuel Quota is
    compared with the summed Fuel Consumption Ledger litres for the same
    vehicle+period. If consumption exceeds ``monthly_litres`` by more than the
    ``OVERAGE_MARGIN`` tolerance, an "Excessive Topup" Operations Alert is raised
    referencing the vehicle. Idempotent per vehicle+period within the month.

    Per-row try/except isolates failures; no commit inside the loop. The alert is
    inserted directly (no import of ``salis.tasks``) to avoid coupling.
    """
    from frappe.utils import flt, now_datetime, today

    period_month = _period_month(today())
    logger = frappe.logger()

    start = 0
    while True:
        quotas = frappe.get_all(
            "Fuel Quota",
            filters={
                "docstatus": 1,
                "status": "Active",
                "period_month": period_month,
            },
            fields=["name", "vehicle", "driver", "monthly_litres"],
            limit_start=start,
            limit_page_length=BATCH_SIZE,
        )
        if not quotas:
            break

        for quota in quotas:
            try:
                if not quota.vehicle:
                    continue

                quota_litres = flt(quota.monthly_litres)
                consumed = frappe.db.sql(
                    """
                    SELECT COALESCE(SUM(litres), 0)
                    FROM `tabFuel Consumption Ledger`
                    WHERE vehicle = %(vehicle)s AND period_month = %(period)s
                    """,
                    {"vehicle": quota.vehicle, "period": period_month},
                )[0][0]
                consumed = flt(consumed)

                threshold = quota_litres * (1 + OVERAGE_MARGIN)
                if quota_litres <= 0 or consumed <= threshold:
                    continue

                if _alert_already_raised(quota.vehicle, period_month):
                    continue

                overage = consumed - quota_litres
                message = frappe._(
                    "Fuel consumption {0} L for vehicle {1} in period {2} exceeds the "
                    "monthly quota of {3} L by {4} L (quota {5})."
                ).format(
                    round(consumed, 2),
                    quota.vehicle,
                    period_month,
                    round(quota_litres, 2),
                    round(overage, 2),
                    quota.name,
                )

                frappe.get_doc(
                    {
                        "doctype": ALERT_DOCTYPE,
                        "alert_type": "Excessive Topup",
                        "severity": "Critical",
                        "status": "Open",
                        "raised_on": now_datetime(),
                        "vehicle": quota.vehicle,
                        "driver": quota.driver,
                        "message": message[:2000],
                    }
                ).insert(ignore_permissions=True)  # audit-ok
            except Exception:
                frappe.db.rollback()
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=f"Fuel reconciliation failed for quota {quota.name}"[:140],
                )

        start += BATCH_SIZE

    logger.info("monthly_fuel_reconciliation: quota reconciliation complete.")
