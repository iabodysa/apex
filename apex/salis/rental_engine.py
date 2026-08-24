# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.query_builder.functions import Coalesce, Sum
from frappe.utils import add_months, flt, fmt_money, get_first_day, get_last_day, getdate, today

from apex.apex_core.utils.company import display_currency, resolve_company
from apex.salis.tasks.common import _queue_document, _reconcile_queue


LEDGER_DOCTYPE = "Rental Accrual Ledger"
BATCH_SIZE = 500


def _currently_received(
    vehicles: list[str], posting_date: str
) -> dict[str, tuple[str | None, float, str | None]]:
    latest: dict = {}
    for row in frappe.get_all(
        "Rental Vehicle Movement",
        filters={
            "vehicle": ["in", vehicles],
            "docstatus": 1,
            "movement_date": ["<=", posting_date],
        },
        fields=["name", "vehicle", "movement_type", "rental_office", "daily_rate"],
        order_by="movement_date desc, creation desc",
    ):
        latest.setdefault(row.vehicle, row)
    return {
        vehicle: (row.rental_office, flt(row.daily_rate), row.name)
        for vehicle, row in latest.items()
        if row.movement_type == "Receipt"
    }


def daily_rental_accrual() -> None:
    posting_date = today()
    logger = frappe.logger()

    _default_company = resolve_company("Salis")

    start = 0
    batch_size = 500
    while True:
        vehicles = frappe.get_all(
            "Salis Vehicle",
            filters={"ownership": "Rented"},
            fields=["name", "company"],
            limit_start=start,
            limit_page_length=batch_size,
        )
        if not vehicles:
            break

        vehicle_names = [vehicle_row.name for vehicle_row in vehicles]
        accrued = set(
            frappe.get_all(
                LEDGER_DOCTYPE,
                filters={"vehicle": ["in", vehicle_names], "accrual_date": posting_date},
                pluck="vehicle",
            )
        )
        received = _currently_received(vehicle_names, posting_date)

        for vehicle_row in vehicles:
            vehicle = vehicle_row.name
            sp = "accrual_row"
            frappe.db.savepoint(sp)
            try:
                if vehicle in accrued:
                    continue

                if vehicle not in received:
                    continue
                rental_office, daily_rate, movement_name = received[vehicle]

                if movement_name:
                    source_doctype = "Rental Vehicle Movement"
                    source_name = movement_name
                else:
                    source_doctype = "Salis Vehicle"
                    source_name = vehicle

                company = vehicle_row.company or _default_company

                frappe.get_doc(
                    {
                        "doctype": "Rental Accrual Ledger",
                        "vehicle": vehicle,
                        "rental_office": rental_office,
                        "company": company,
                        "accrual_date": posting_date,
                        "daily_rate": daily_rate,
                        "amount": daily_rate,
                        "settled": 0,
                        "source_doctype": source_doctype,
                        "source_name": source_name,
                    }
                ).insert()
            except Exception:
                frappe.db.rollback(save_point=sp)
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=f"Rental accrual failed for vehicle {vehicle}"[:140],
                )

        start += batch_size

    logger.info("daily_rental_accrual: rental accrual memos written.")


def reverse_rental_accrual(source_doctype: str, source_name: str) -> int:
    originals = frappe.get_all(
        LEDGER_DOCTYPE,
        filters={
            "source_doctype": source_doctype,
            "source_name": source_name,
            "reversal_of": ["is", "not set"],
        },
        fields=["name", "vehicle", "rental_office", "company", "accrual_date", "amount"],
    )

    posted = 0
    for row in originals:
        if frappe.db.exists(LEDGER_DOCTYPE, {"reversal_of": row.name}):
            continue

        frappe.get_doc(
            {
                "doctype": LEDGER_DOCTYPE,
                "vehicle": row.vehicle,
                "rental_office": row.rental_office,
                "company": row.company,
                "accrual_date": row.accrual_date,
                "amount": -flt(row.amount),
                "source_doctype": source_doctype,
                "reversal_of": row.name,
            }
        ).insert(ignore_permissions=True)
        posted += 1

    return posted


def _period_bounds(period_month: str) -> tuple[str, str] | None:
    if not period_month:
        return None
    try:
        anchor = getdate(str(period_month).strip()[:7] + "-01")
    except Exception:
        return None
    return str(get_first_day(anchor)), str(get_last_day(anchor))


def _settlement_row_filters(rental_office: str, period_month: str) -> dict | None:
    if not rental_office:
        return None
    bounds = _period_bounds(period_month)
    if not bounds:
        return None
    first_day, last_day = bounds
    return {
        "rental_office": rental_office,
        "accrual_date": ["between", [first_day, last_day]],
        "reversal_of": ["is", "not set"],
    }


def linked_accrued_total(rental_office: str, period_month: str) -> float:
    bounds = _period_bounds(period_month)
    if not rental_office or not bounds:
        return 0.0
    first_day, last_day = bounds
    RAL = frappe.qb.DocType("Rental Accrual Ledger")
    total = (
        frappe.qb.from_(RAL)
        .select(Coalesce(Sum(RAL.amount), 0))
        .where(RAL.rental_office == rental_office)
        .where(RAL.accrual_date.between(first_day, last_day))
        .where((RAL.reversal_of.isnull()) | (RAL.reversal_of == ""))
    ).run()[0][0]
    return flt(total)


def stamp_settlement(settlement: str, rental_office: str, period_month: str) -> int:
    filters = _settlement_row_filters(rental_office, period_month)
    if not filters:
        return 0

    filters = dict(filters)
    filters["settled"] = 0

    names = frappe.get_all(LEDGER_DOCTYPE, filters=filters, pluck="name")
    if not names:
        return 0

    frappe.db.set_value(
        LEDGER_DOCTYPE,
        {"name": ["in", names]},
        {"rental_settlement": settlement, "settled": 1},
        update_modified=False,
    )
    return len(names)


def release_settlement(settlement: str) -> int:
    if not settlement:
        return 0
    names = frappe.get_all(
        LEDGER_DOCTYPE, filters={"rental_settlement": settlement}, pluck="name"
    )
    if not names:
        return 0
    frappe.db.set_value(
        LEDGER_DOCTYPE,
        {"name": ["in", names]},
        {"rental_settlement": None, "settled": 0},
        update_modified=False,
    )
    return len(names)


def monthly_rental_reconciliation() -> None:
    closed_anchor = getdate(add_months(getdate(today()), -1))
    period_month = str(closed_anchor)[:7]
    first_day, last_day = str(get_first_day(closed_anchor)), str(get_last_day(closed_anchor))
    logger = frappe.logger()

    RAL = frappe.qb.DocType("Rental Accrual Ledger")
    rows = (
        frappe.qb.from_(RAL)
        .select(RAL.rental_office, Coalesce(Sum(RAL.amount), 0).as_("outstanding"))
        .where(RAL.settled == 0)
        .where((RAL.reversal_of.isnull()) | (RAL.reversal_of == ""))
        .where(RAL.accrual_date.between(first_day, last_day))
        .where(RAL.rental_office.isnotnull())
        .where(RAL.rental_office != "")
        .groupby(RAL.rental_office)
    ).run(as_dict=True)

    still_unsettled: list[str] = []
    for row in rows:
        rental_office = row.rental_office
        sp = "accrual_row"
        frappe.db.savepoint(sp)
        try:
            if not rental_office:
                continue

            outstanding = flt(row.outstanding)
            message = frappe._(
                "Rental accrual for office {0} in period {1} is unsettled: "
                "{2} outstanding with no submitted Rental Settlement. "
                "(office {0})"
            ).format(
                rental_office,
                period_month,
                fmt_money(outstanding, currency=display_currency("Salis")),
            )

            _queue_document("Rental Office", rental_office, "Warning", message)
            still_unsettled.append(rental_office)
        except Exception:
            frappe.db.rollback(save_point=sp)
            frappe.log_error(
                message=frappe.get_traceback(),
                title=f"Rental reconciliation failed for office {rental_office}"[:140],
            )

    _reconcile_queue("Rental Office", still_unsettled)

    logger.info("monthly_rental_reconciliation: unsettled rental accrual flagged.")
