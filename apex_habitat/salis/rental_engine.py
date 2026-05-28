"""Rental accrual engine for the Salis fleet module.

Background engine — never hand-entered. Mirrors the Habitat daily cost
allocation pattern (``apex_habitat.habitat.tasks.daily_accommodation_cost_allocation``):
idempotent, per-row error isolation, no commit inside the loop, and inserts
with ignore_permissions because the target ledger grants no human write role.

Posts NO General Ledger / accounting entry: each Rental Accrual Ledger row is
an operational memo, the source for monthly Rental Settlement reconciliation.

Scheduler hook (daily):
    apex_habitat.salis.rental_engine.daily_rental_accrual
"""

from __future__ import annotations

import frappe
from frappe.utils import flt, today


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

    start = 0
    batch_size = 500
    while True:
        vehicles = frappe.get_all(
            "Salis Vehicle",
            filters={"ownership": "Rented"},
            pluck="name",
            limit_start=start,
            limit_page_length=batch_size,
        )
        if not vehicles:
            break

        for vehicle in vehicles:
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

                frappe.get_doc(
                    {
                        "doctype": "Rental Accrual Ledger",
                        "vehicle": vehicle,
                        "rental_office": rental_office,
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
