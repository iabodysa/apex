# Copyright (c) 2026, afmcoltd


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
    percent = get_salis_int("fuel_overage_margin_percent", OVERAGE_MARGIN_DEFAULT_PERCENT)
    return percent / 100.0

def _period_month(date_value) -> str:
    return str(date_value)[:7]


def reverse_fuel_ledger(source_type: str, source_name: str) -> int:
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
                "source_type": source_type,
                "source_doctype": source_type,
                "source_name": source_name,
                "logged_at": now_datetime(),
                "reversal_of": row.name,
            }
        ).insert()
        posted += 1

    return posted

def accrue_fuel_consumption() -> None:
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
                    ).insert()
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
                ).insert()
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
