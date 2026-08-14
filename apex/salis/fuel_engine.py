# Copyright (c) 2026, afmcoltd

"""Fuel engine for the Salis Movement module.

Background engine that mirrors the Habitat no-GL, system-written ledger pattern
(``apex.habitat.doctype.accommodation_ledger``) and the batch/idempotent
scheduled-job style in ``apex.habitat.tasks``.

The inserts pass ``ignore_permissions`` for the same reason the rental engine's do: the scheduler
runs with no session user, and the Fuel Consumption Ledger grants no human write role at all. A
DocPerm that made these legal would also let an operator write accrual rows by hand.

Two scheduled jobs:

* ``accrue_fuel_consumption`` (daily) — accrues a Fuel Consumption Ledger row for
  each recent Fuel Daily Log and each Done Fuel Request not yet ledgered.
  Idempotent on ``(source_type, source_name)``.
* ``monthly_fuel_reconciliation`` (monthly) — for each active Fuel Quota of the
  period, sums ledgered consumption for that vehicle+period against the quota's
  monthly litres; if consumption exceeds the quota beyond a tolerance margin the
  breached Fuel Quota is ASSIGNED to the Fleet Supervisor queue. Idempotent by the
  framework's own rule (one open assignment per quota+holder); the queue drains in
  ``reconcile_operations_alerts`` once the breach clears.

No GL is written. The queue helper is imported inside the job so module load keeps
no ``salis.tasks`` coupling.
"""

from __future__ import annotations

import frappe
from frappe.query_builder.functions import Coalesce, Sum

from apex.apex_core.utils.company import company_for_vehicle


LEDGER_DOCTYPE = "Fuel Consumption Ledger"
BATCH_SIZE = 500

OVERAGE_MARGIN = 0.05
OVERAGE_MARGIN_DEFAULT_PERCENT = 5


def get_overage_margin() -> float:
    """Return the fuel-quota overage margin as a fraction (e.g. 0.05 for 5%).

    Reads the Int percent ``fuel_overage_margin_percent`` from Salis Settings via
    the zero-trap helper and divides by 100, so a blank/0 setting keeps today's 5%."""
    from apex.apex_core.doctype.salis_settings.salis_settings import get_salis_int

    percent = get_salis_int("fuel_overage_margin_percent", OVERAGE_MARGIN_DEFAULT_PERCENT)
    return percent / 100.0


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
            "company": company_for_vehicle(vehicle),
            "period_month": period_month,
            "litres": litres,
            "amount": amount,
            "source_type": source_type,
            "source_doctype": source_type,
            "source_name": source_name,
            "logged_at": logged_at,
        }
    ).insert(ignore_permissions=True)


def reverse_fuel_ledger(source_type: str, source_name: str) -> int:
    """Reverse the ledgered consumption for a corrected/cancelled fuel source.

    When a fuel source (a Fuel Request whose Done row was already ledgered, or a
    Fuel Daily Log) is cancelled or deleted, its consumption must not stay in the
    Fuel Consumption Ledger. This posts a negative mirror row for each original
    ledger row of that source — negating ``litres`` and ``amount`` — and links it
    back via ``reversal_of``, so the source nets to zero in every consumption sum
    while the original row is preserved for audit.

    This mirrors the Habitat ledger reversal idiom (``Accommodation Ledger`` via
    ``utility_bill_entry.before_cancel``): a negated row with ``reversal_of`` set,
    not a delete. The Fuel Consumption Ledger carries no ``is_cancelled`` flag, so
    — exactly like the Accommodation Ledger — the guard against double-reversal is
    that only an ORIGINAL row (``reversal_of`` unset) is ever mirrored, and a row
    that already has a reversal pointing at it is skipped.

    Idempotent: calling it twice for the same source posts at most one reversal
    per original row. Returns the number of reversal rows posted (0 if the source
    was never ledgered or is already fully reversed).
    """
    from frappe.utils import flt, now_datetime

    originals = frappe.get_all(
        LEDGER_DOCTYPE,
        filters={
            "source_type": source_type,
            "source_name": source_name,
            "reversal_of": ["is", "not set"],
        },
        fields=[
            "name",
            "vehicle",
            "driver",
            "company",
            "period_month",
            "litres",
            "amount",
        ],
    )

    posted = 0
    for row in originals:
        if frappe.db.exists(LEDGER_DOCTYPE, {"reversal_of": row.name}):
            continue

        frappe.get_doc(
            {
                "doctype": LEDGER_DOCTYPE,
                "vehicle": row.vehicle,
                "driver": row.driver,
                "company": row.company,
                "period_month": row.period_month,
                "litres": -flt(row.litres),
                "amount": -flt(row.amount),
                "source_doctype": source_type,
                "logged_at": now_datetime(),
                "reversal_of": row.name,
            }
        ).insert(ignore_permissions=True)
        posted += 1

    return posted


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
            sp = "accrual_row"
            frappe.db.savepoint(sp)
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
                frappe.db.rollback(save_point=sp)
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=f"Fuel accrual failed for Daily Log {log.name}"[:140],
                )

        start += BATCH_SIZE

    failed_names: set[str] = set()
    while True:
        filters = {
            "docstatus": 1,
            "status": "Done",
            "ledgered": 0,
        }
        if failed_names:
            filters["name"] = ["not in", list(failed_names)]
        requests = frappe.get_all(
            "Fuel Request",
            filters=filters,
            fields=["name", "vehicle", "driver", "request_date", "requested_litres", "amount"],
            order_by="modified asc",
            limit_page_length=BATCH_SIZE,
        )
        if not requests:
            break

        progressed = False
        for req in requests:
            sp = "accrual_row"
            frappe.db.savepoint(sp)
            try:
                if not req.vehicle:
                    frappe.db.set_value(
                        "Fuel Request", req.name, "ledgered", 1, update_modified=False
                    )
                    progressed = True
                    continue
                if _ledger_exists("Fuel Request", req.name):
                    frappe.db.set_value(
                        "Fuel Request", req.name, "ledgered", 1, update_modified=False
                    )
                    progressed = True
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
                frappe.db.set_value(
                    "Fuel Request", req.name, "ledgered", 1, update_modified=False
                )
                progressed = True
            except Exception:
                frappe.db.rollback(save_point=sp)
                failed_names.add(req.name)
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=f"Fuel accrual failed for Request {req.name}"[:140],
                )

        if not progressed:
            break

    logger.info("accrue_fuel_consumption: fuel consumption ledger updated.")


def monthly_fuel_reconciliation() -> None:
    """Reconcile each active Fuel Quota's allocation against ledgered consumption.

    For the current period (this month, YYYY-MM), every active Fuel Quota is
    compared with the summed Fuel Consumption Ledger litres for the same
    vehicle+period. If consumption exceeds ``monthly_litres`` by more than the
    ``OVERAGE_MARGIN`` tolerance, the breached Fuel Quota — the document whose
    allocation the supervisor must revisit — is ASSIGNED to the Fleet Supervisor
    queue. Idempotent by the framework's assignment dedupe; the queue drains in
    ``reconcile_operations_alerts`` once the breach clears.

    Per-row try/except isolates failures; no commit inside the loop.
    """
    from frappe.utils import flt, today

    from apex.salis.tasks.common import _queue_document

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
            sp = "accrual_row"
            frappe.db.savepoint(sp)
            try:
                if not quota.vehicle:
                    continue

                quota_litres = flt(quota.monthly_litres)
                FCL = frappe.qb.DocType("Fuel Consumption Ledger")
                consumed = (
                    frappe.qb.from_(FCL)
                    .select(Coalesce(Sum(FCL.litres), 0))
                    .where(FCL.vehicle == quota.vehicle)
                    .where(FCL.period_month == period_month)
                ).run()[0][0]
                consumed = flt(consumed)

                threshold = quota_litres * (1 + get_overage_margin())
                if quota_litres <= 0 or consumed <= threshold:
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

                _queue_document(
                    "Fuel Quota", quota.name, "Critical", message, vehicle=quota.vehicle,
                )
            except Exception:
                frappe.db.rollback(save_point=sp)
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=f"Fuel reconciliation failed for quota {quota.name}"[:140],
                )

        start += BATCH_SIZE

    logger.info("monthly_fuel_reconciliation: quota reconciliation complete.")
