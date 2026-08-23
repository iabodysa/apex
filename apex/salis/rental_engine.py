# Copyright (c) 2026, afmcoltd
"""Rental accrual engine for the Salis fleet module.

Background engine — never hand-entered. Mirrors the Habitat daily cost
allocation pattern (``apex.habitat.tasks.daily_accommodation_cost_allocation``):
idempotent, per-row error isolation, no commit inside the loop, and inserts
with ignore_permissions because the target ledger grants no human write role.

Posts NO General Ledger / accounting entry: each Rental Accrual Ledger row is
an operational memo, the source for monthly Rental Settlement reconciliation.

Reconciliation (the second half of the documented loop) is the mirror of the
fuel engine's reconciliation idiom (``fuel_engine``):

* When a Rental Settlement is submitted/approved, its accrual rows for the same
  rental_office + period are stamped settled (``stamp_settlement`` →
  ``frappe.db.set_value``; the ledger grants no human write role, so the bypass
  is correct). Cancelling the settlement releases them again.
* ``monthly_rental_reconciliation`` (monthly) ASSIGNS any Rental Office that still
  has unsettled accrual rows for the just-closed period to the Fleet Supervisor
  queue — exactly as ``monthly_fuel_reconciliation`` queues over-quota Fuel
  Quotas — and reconciles that queue at the end of the pass so a settled office
  drains on the next run.

Scheduler hooks:
    apex.salis.rental_engine.daily_rental_accrual           (daily)
    apex.salis.rental_engine.monthly_rental_reconciliation  (monthly)
"""

from __future__ import annotations

import frappe
from frappe.query_builder.functions import Coalesce, Sum
from frappe.utils import flt, fmt_money, today

from apex.apex_core.utils.company import display_currency


LEDGER_DOCTYPE = "Rental Accrual Ledger"
BATCH_SIZE = 500


def _currently_received(
    vehicles: list[str], posting_date: str
) -> dict[str, tuple[str | None, float, str | None]]:
    """A rented vehicle is in-service when its latest submitted Rental Vehicle
    Movement on or before ``posting_date`` is a Receipt (i.e. there is an open
    Receipt with no later Return). Returns the in-service vehicles only, keyed
    by vehicle, each mapped to (rental_office, daily_rate, movement_name).
    """
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
    """Post one Rental Accrual Ledger memo per in-service rented vehicle for today.

    For each Salis Vehicle with ownership == "Rented" that is currently received
    (latest submitted movement is a Receipt with no later Return), insert one
    Rental Accrual Ledger row dated today with amount = daily_rate. Idempotent:
    skips any vehicle that already has a row for today.
    """
    posting_date = today()
    logger = frappe.logger()

    from apex.apex_core.utils.company import resolve_company

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
                ).insert(ignore_permissions=True)
            except Exception:
                frappe.db.rollback(save_point=sp)
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=f"Rental accrual failed for vehicle {vehicle}"[:140],
                )

        start += batch_size

    logger.info("daily_rental_accrual: rental accrual memos written.")


def reverse_rental_accrual(source_doctype: str, source_name: str) -> int:
    """Reverse the ledgered accrual for a corrected/cancelled rental source.

    When a Receipt Rental Vehicle Movement is cancelled, the daily accrual rows it
    produced (every day the vehicle stayed in-service under that Receipt) must not
    survive it — an accrued day whose Receipt no longer exists still gets settled
    and paid otherwise. Mirrors ``fuel_engine.reverse_fuel_ledger``: a negative
    mirror row per original, dated the SAME ``accrual_date`` as the row it negates
    (a Receipt spans many days, so one shared date would misplace the reversal into
    the wrong settlement period) and linked back via ``reversal_of``, so the source
    nets to zero while the original rows are preserved for audit.

    Idempotent: only an ORIGINAL row (``reversal_of`` unset) is ever mirrored, and a
    row that already has a reversal pointing at it is skipped, so calling this twice
    for the same source posts at most one reversal per original row. Returns the
    number of reversal rows posted (0 if the source was never accrued or is already
    fully reversed).
    """
    from frappe.utils import flt

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
    """Return (first_day, last_day) as YYYY-MM-DD for a "YYYY-MM" period string,
    or None when the period is blank/unparseable. The accrual rows carry a full
    ``accrual_date``; the settlement carries a "YYYY-MM" ``period_month``, so a
    settlement's rows are those whose accrual_date falls inside this window.
    """
    from frappe.utils import get_first_day, get_last_day, getdate

    if not period_month:
        return None
    try:
        anchor = getdate(str(period_month).strip()[:7] + "-01")
    except Exception:
        return None
    return str(get_first_day(anchor)), str(get_last_day(anchor))


def _settlement_row_filters(rental_office: str, period_month: str) -> dict | None:
    """The selector for the Rental Accrual Ledger rows a settlement owns: same
    rental_office, accrual_date inside the period, and ORIGINAL rows only
    (``reversal_of`` unset — a reversal memo is never settled). Returns None when
    the office or period is missing/unparseable (nothing to stamp)."""
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
    """Sum the ORIGINAL Rental Accrual Ledger amount for an office+period.

    This is the ledger-derived accrued figure the Rental Settlement controller
    cross-checks its hand-entered vehicle lines against — the source of truth for
    "what the rental engine actually accrued" for this office and month.
    """
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
    """Stamp the unsettled accrual rows for an office+period onto a settlement.

    For every Rental Accrual Ledger row of ``rental_office`` whose accrual_date is
    in ``period_month``, that is still ``settled = 0`` and not already linked to
    another settlement, set ``rental_settlement = settlement`` and ``settled = 1``
    via ``frappe.db.set_value`` (the ledger grants no human write role, so the
    permission bypass is correct — same idiom as the engine's inserts).

    Idempotent / no double-stamp: rows already settled (``settled = 1``) are
    excluded by the filter, so a second call for the same settlement finds none
    and is a no-op. A row linked to a DIFFERENT settlement is also excluded — it
    is never silently re-pointed. Returns the number of rows stamped.
    """
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
    """Release every accrual row currently linked to ``settlement``.

    The mirror of :func:`stamp_settlement`, used when a settlement is cancelled
    (or amended): rows stamped to it are set back to ``settled = 0`` and their
    ``rental_settlement`` link cleared, so the Rental Cost by Office report stops
    counting them as settled and a re-issued settlement can claim them again.
    Idempotent: a settlement with no linked rows yields 0. Returns the count
    released.
    """
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
    """Flag rental offices with unsettled accrual rows for the closed period.

    Mirrors ``fuel_engine.monthly_fuel_reconciliation``: for the period that has
    just closed (last month, YYYY-MM), every Rental Office that still has
    ORIGINAL Rental Accrual Ledger rows with ``settled = 0`` — i.e. no submitted
    Rental Settlement has claimed that office's accrued days — is ASSIGNED to the
    Fleet Supervisor queue, the assignment carrying the outstanding amount.
    Idempotent by the framework's assignment dedupe. This job is the only queuer
    of Rental Office, so its own findings are the reconcile union: an office that
    settles drains from the queue on the next monthly pass.

    Reconciliation only — posts no GL and stamps nothing (stamping is the
    settlement's job, via :func:`stamp_settlement`). Per-row try/except isolates
    failures; no commit inside the loop.
    """
    from frappe.utils import add_months, get_first_day, get_last_day, getdate

    from apex.salis.tasks.common import _queue_document, _reconcile_queue

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
