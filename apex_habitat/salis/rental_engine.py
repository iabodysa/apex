"""Rental accrual engine for the Salis fleet module.

Background engine — never hand-entered. Mirrors the Habitat daily cost
allocation pattern (``apex_habitat.habitat.tasks.daily_accommodation_cost_allocation``):
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
* ``monthly_rental_reconciliation`` (monthly) flags any Rental Office that still
  has unsettled accrual rows for the just-closed period with an Operations
  Alert — exactly as ``monthly_fuel_reconciliation`` flags over-quota vehicles.

Scheduler hooks:
    apex_habitat.salis.rental_engine.daily_rental_accrual           (daily)
    apex_habitat.salis.rental_engine.monthly_rental_reconciliation  (monthly)
"""

from __future__ import annotations

import frappe
from frappe.utils import flt, today

LEDGER_DOCTYPE = "Rental Accrual Ledger"
ALERT_DOCTYPE = "Operations Alert"
BATCH_SIZE = 500


def _is_currently_received(
    vehicle: str, posting_date: str
) -> tuple[bool, str | None, float, str | None]:
    """A rented vehicle is in-service when its latest submitted Rental Vehicle
    Movement on or before ``posting_date`` is a Receipt (i.e. there is an open
    Receipt with no later Return). Returns
    (in_service, rental_office, daily_rate, movement_name).
    """
    latest = frappe.get_all(
        "Rental Vehicle Movement",
        filters={
            "vehicle": vehicle,
            "docstatus": 1,
            "movement_date": ["<=", posting_date],
        },
        fields=["name", "movement_type", "rental_office", "daily_rate"],
        order_by="movement_date desc, creation desc",
        limit_page_length=1,
    )
    if not latest:
        return False, None, 0.0, None
    row = latest[0]
    if row.movement_type != "Receipt":
        return False, None, 0.0, None
    return True, row.rental_office, flt(row.daily_rate), row.name


def daily_rental_accrual() -> None:
    """Post one Rental Accrual Ledger memo per in-service rented vehicle for today.

    For each Salis Vehicle with ownership == "Rented" that is currently received
    (latest submitted movement is a Receipt with no later Return), insert one
    Rental Accrual Ledger row dated today with amount = daily_rate. Idempotent:
    skips any vehicle that already has a row for today.
    """
    posting_date = today()
    logger = frappe.logger()

    # Resolved once per run as the fallback when a vehicle has no company set.
    from apex_habitat.apex_core.doctype.salis_settings.salis_settings import get_default_company

    _default_company = get_default_company()

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

        for vehicle_row in vehicles:
            vehicle = vehicle_row.name
            try:
                # Idempotence: one row per vehicle per day.
                if frappe.db.exists(
                    "Rental Accrual Ledger",
                    {"vehicle": vehicle, "accrual_date": posting_date},
                ):
                    continue

                in_service, rental_office, daily_rate, movement_name = (
                    _is_currently_received(vehicle, posting_date)
                )
                if not in_service:
                    continue

                # Source traceability: the originating record is the open
                # Rental Vehicle Movement (Receipt) when known, else the vehicle.
                if movement_name:
                    source_doctype = "Rental Vehicle Movement"
                    source_name = movement_name
                else:
                    source_doctype = "Salis Vehicle"
                    source_name = vehicle

                # Carry the owning company for reporting grouping: the vehicle's
                # own company, else the Salis Settings default. Reference only -
                # this memo posts no GL.
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
                ).insert(ignore_permissions=True)  # audit-ok
            except Exception:
                frappe.db.rollback()
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=f"Rental accrual failed for vehicle {vehicle}"[:140],
                )

        start += batch_size

    logger.info("daily_rental_accrual: rental accrual memos written.")


# ---------------------------------------------------------------------------
# Settlement stamping (Rental Accrual Ledger -> Rental Settlement link)
# ---------------------------------------------------------------------------


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
    # Raw aggregate (mirrors fuel_engine's SUM): frappe.get_all forbids SQL
    # functions in `fields`. Original rows only (reversal_of NULL) so a reversal
    # memo never inflates the accrued figure.
    total = frappe.db.sql(
        """
        SELECT COALESCE(SUM(amount), 0)
        FROM `tabRental Accrual Ledger`
        WHERE rental_office = %(office)s
          AND accrual_date BETWEEN %(first)s AND %(last)s
          AND (reversal_of IS NULL OR reversal_of = '')
        """,
        {"office": rental_office, "first": first_day, "last": last_day},
    )[0][0]
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

    # No-double-stamp guard: only rows that are still UNSETTLED are eligible.
    # ``settled = 0`` is the authoritative "not yet stamped" marker — stamping
    # always sets ``settled = 1`` and the link together (and release resets both
    # together), so a ``settled = 0`` row is by construction owned by no
    # settlement. This both makes the operation idempotent (a second call for
    # this settlement finds its rows already settled and skips them) and never
    # re-points a row already claimed by another settlement (it is settled = 1,
    # hence excluded). Keying on settled = 0 also sidesteps the SQL NULL-vs-IN
    # trap: a freshly accrued row has rental_settlement = NULL, which an
    # ``["in", [None, ...]]`` filter would silently miss.
    filters = dict(filters)
    filters["settled"] = 0

    names = frappe.get_all(LEDGER_DOCTYPE, filters=filters, pluck="name")
    if not names:
        return 0

    # update_modified=False keeps the machine-written memo's audit timestamp
    # stable; the link + flag are system metadata, not a content edit.
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


# ---------------------------------------------------------------------------
# Monthly reconciliation
# ---------------------------------------------------------------------------


def _rental_alert_already_raised(rental_office: str, period_month: str) -> bool:
    """True if an Unsettled-Rental alert was already raised for this office+period.

    Idempotency key = (alert_type, the office AND period stamped in the message).
    Operations Alert has no rental_office / period link field, so both are encoded
    in the message (``... period <YYYY-MM> ... (office <name>)``) and matched
    there. Unlike the fuel engine's raised-on-month-window guard, a raised-on
    window is deliberately NOT used: this job reconciles the CLOSED (previous)
    month but raises the alert in the CURRENT month, so a period-month window
    would never contain its own alert and the job would duplicate every run. The
    office+period pair in the message is itself the unique key.
    """
    period = str(period_month).strip()[:7]
    return bool(
        frappe.db.exists(
            ALERT_DOCTYPE,
            {
                "alert_type": "Unsettled Rental",
                "message": ["like", f"%period {period}%(office {rental_office})%"],
            },
        )
    )


def monthly_rental_reconciliation() -> None:
    """Flag rental offices with unsettled accrual rows for the closed period.

    Mirrors ``fuel_engine.monthly_fuel_reconciliation``: for the period that has
    just closed (last month, YYYY-MM), every Rental Office that still has
    ORIGINAL Rental Accrual Ledger rows with ``settled = 0`` — i.e. no submitted
    Rental Settlement has claimed that office's accrued days — raises an
    "Unsettled Rental" Operations Alert carrying the outstanding amount.
    Idempotent per office+period within the month (``_rental_alert_already_raised``).

    Reconciliation only — posts no GL and stamps nothing (stamping is the
    settlement's job, via :func:`stamp_settlement`). Per-row try/except isolates
    failures; no commit inside the loop. The alert is inserted directly (no
    import of ``salis.tasks``) to avoid coupling, exactly as the fuel engine does.
    """
    from frappe.utils import add_months, get_first_day, get_last_day, getdate, now_datetime

    # The CLOSED period is last month, so a settlement raised early in the new
    # month has time to land before the office is flagged.
    closed_anchor = getdate(add_months(getdate(today()), -1))
    period_month = str(closed_anchor)[:7]
    first_day, last_day = str(get_first_day(closed_anchor)), str(get_last_day(closed_anchor))
    logger = frappe.logger()

    # Offices that still have unsettled ORIGINAL accrual rows in the closed
    # period, with the outstanding sum per office. Raw aggregate (frappe.get_all
    # forbids SQL functions in `fields`); mirrors fuel_engine's SUM idiom.
    rows = frappe.db.sql(
        """
        SELECT rental_office, COALESCE(SUM(amount), 0) AS outstanding
        FROM `tabRental Accrual Ledger`
        WHERE settled = 0
          AND (reversal_of IS NULL OR reversal_of = '')
          AND accrual_date BETWEEN %(first)s AND %(last)s
          AND rental_office IS NOT NULL AND rental_office != ''
        GROUP BY rental_office
        """,
        {"first": first_day, "last": last_day},
        as_dict=True,
    )

    for row in rows:
        rental_office = row.rental_office
        try:
            if not rental_office:
                continue
            if _rental_alert_already_raised(rental_office, period_month):
                continue

            outstanding = flt(row.outstanding)
            message = frappe._(
                "Rental accrual for office {0} in period {1} is unsettled: "
                "{2} SAR outstanding with no submitted Rental Settlement. "
                "(office {0})"
            ).format(rental_office, period_month, round(outstanding, 2))

            frappe.get_doc(
                {
                    "doctype": ALERT_DOCTYPE,
                    "alert_type": "Unsettled Rental",
                    "severity": "Warning",
                    "status": "Open",
                    "raised_on": now_datetime(),
                    "message": message[:2000],
                }
            ).insert(ignore_permissions=True)  # audit-ok
        except Exception:
            frappe.db.rollback()
            frappe.log_error(
                message=frappe.get_traceback(),
                title=f"Rental reconciliation failed for office {rental_office}"[:140],
            )

    logger.info("monthly_rental_reconciliation: unsettled rental accrual flagged.")
