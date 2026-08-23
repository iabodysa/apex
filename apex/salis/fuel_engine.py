# Copyright (c) 2026, afmcoltd

"""Fuel engine for the Salis Movement module.

Background engine that mirrors the Habitat no-GL, system-written ledger pattern
(``apex.habitat.doctype.accommodation_ledger``) and the batch/idempotent
scheduled-job style in ``apex.habitat.tasks``.

The inserts pass ``ignore_permissions``, which is ERPNext's own idiom for an immutable subledger —
``general_ledger.py:412`` sets the same flag on GL Entry. The DocType carries ``in_create``, which
removes the New button but refuses nothing on the server (``frappe/utils/user.py:112,172``). The
refusal is in the DocPerm rows: every role on Fuel Consumption Ledger has ``read`` and nothing
else, System Manager included. So this bypass is the only path by which a row can exist.

Two scheduled jobs:

* ``accrue_fuel_consumption`` (daily) — accrues a Fuel Consumption Ledger row for
  each Fuel Daily Log and each Done Fuel Request not yet ledgered, however old.
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
from frappe.utils import add_months, flt, getdate, now_datetime, today

from apex.apex_core.doctype.salis_settings.salis_settings import get_salis_int
from apex.apex_core.utils.company import company_for_vehicle
from apex.salis.tasks.common import _queue_document, _reconcile_queue

LEDGER_DOCTYPE = "Fuel Consumption Ledger"
BATCH_SIZE = 500

OVERAGE_MARGIN_DEFAULT_PERCENT = 5

def get_overage_margin() -> float:
    """Return the fuel-quota overage margin as a fraction (e.g. 0.05 for 5%).

    Reads the Int percent ``fuel_overage_margin_percent`` from Salis Settings via
    the zero-trap helper and divides by 100, so a blank/0 setting keeps today's 5%."""
    percent = get_salis_int("fuel_overage_margin_percent", OVERAGE_MARGIN_DEFAULT_PERCENT)
    return percent / 100.0

def _period_month(date_value) -> str:
    """Return the YYYY-MM period string for a date/datetime value."""
    return str(date_value)[:7]


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

    * Fuel Daily Log rows not yet ledgered.
    * Fuel Requests in ``Done`` status (submitted) not yet ledgered.

    BOTH halves select on the ``ledgered`` flag, not on a date window. A fixed
    two-day ``log_date`` window silently dropped work rather than deferring it: a log
    backdated past yesterday was never in scope on any run, and one missed scheduler
    day put every log of that day permanently out of reach. The flag turns the job
    into a backlog drain — anything unledgered is picked up on the next run, however
    old — and it is what makes catching up possible at all.

    Idempotent on ``(source_type, source_name)`` as well: a source already carrying a
    ledger row is flagged and skipped rather than double-posted, which is what makes
    the flag safe to introduce on a site whose rows all start at 0. Per-row
    try/except isolates failures; no commit inside the loops.
    """
    logger = frappe.logger()

    failed_logs: set[str] = set()
    while True:
        log_filters = {"ledgered": 0}
        if failed_logs:
            log_filters["name"] = ["not in", list(failed_logs)]
        logs = frappe.get_all(
            "Fuel Daily Log",
            filters=log_filters,
            fields=["name", "vehicle", "driver", "log_date", "litres", "amount"],
            order_by="modified asc",
            limit_page_length=BATCH_SIZE,
        )
        if not logs:
            break

        progressed = False
        for log in logs:
            sp = "accrual_row"
            frappe.db.savepoint(sp)
            try:
                if log.vehicle and not frappe.db.exists(
                    LEDGER_DOCTYPE,
                    {"source_type": "Fuel Daily Log", "source_name": log.name},
                ):
                    frappe.get_doc(
                        {
                            "doctype": LEDGER_DOCTYPE,
                            "vehicle": log.vehicle,
                            "driver": log.driver,
                            "company": company_for_vehicle(log.vehicle),
                            "period_month": _period_month(log.log_date),
                            "litres": flt(log.litres),
                            "amount": flt(log.amount),
                            "source_type": "Fuel Daily Log",
                            "source_doctype": "Fuel Daily Log",
                            "source_name": log.name,
                            "logged_at": now_datetime(),
                        }
                    ).insert(ignore_permissions=True)
                frappe.db.set_value(
                    "Fuel Daily Log", log.name, "ledgered", 1, update_modified=False
                )
                progressed = True
            except Exception:
                frappe.db.rollback(save_point=sp)
                failed_logs.add(log.name)
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=f"Fuel accrual failed for Daily Log {log.name}"[:140],
                )

        if not progressed:
            break

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
                if frappe.db.exists(
                    LEDGER_DOCTYPE,
                    {"source_type": "Fuel Request", "source_name": req.name},
                ):
                    frappe.db.set_value(
                        "Fuel Request", req.name, "ledgered", 1, update_modified=False
                    )
                    progressed = True
                    continue
                frappe.get_doc(
                    {
                        "doctype": LEDGER_DOCTYPE,
                        "vehicle": req.vehicle,
                        "driver": req.driver,
                        "company": company_for_vehicle(req.vehicle),
                        "period_month": _period_month(req.request_date),
                        "litres": flt(req.requested_litres),
                        "amount": flt(req.amount),
                        "source_type": "Fuel Request",
                        "source_doctype": "Fuel Request",
                        "source_name": req.name,
                        "logged_at": now_datetime(),
                    }
                ).insert(ignore_permissions=True)
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

    For the period that has CLOSED, every active Fuel Quota is compared with the
    summed Fuel Consumption Ledger litres for the same vehicle+period. If consumption
    exceeds ``monthly_litres`` by more than the tolerance the operator set in
    ``Salis Settings.fuel_overage_margin_percent``, the
    breached Fuel Quota — the document whose allocation the supervisor must revisit —
    is ASSIGNED to the Fleet Supervisor queue.

    The period is the closed month, not the current one, because this job's only firing
    instant is 00:00 on the 1st: at that moment the month that has just begun holds no
    ledger rows at all (``accrue_fuel_consumption`` is daily), so a current-month
    anchor compared every allocation against ~0 litres and no breach could ever be
    found. This mirrors ``rental_engine.monthly_rental_reconciliation``.

    Idempotent by the framework's assignment dedupe. This job is the only queuer of
    Fuel Quota, so its own findings ARE the reconcile union and it drains its own queue
    in the same pass — which is also why the calendar month cannot drift between the
    two halves the way it did while a daily job owned the drain.

    Per-row try/except isolates failures; no commit inside the loop.
    """
    period_month = _period_month(add_months(getdate(today()), -1))
    logger = frappe.logger()

    breached: list[str] = []
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
                breached.append(quota.name)
            except Exception:
                frappe.db.rollback(save_point=sp)
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=f"Fuel reconciliation failed for quota {quota.name}"[:140],
                )

        start += BATCH_SIZE

    _reconcile_queue("Fuel Quota", breached)

    logger.info("monthly_fuel_reconciliation: quota reconciliation complete.")
