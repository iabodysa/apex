# Copyright (c) 2026, afmcoltd
"""Scheduled tasks for the Habitat module (split by domain).

The ledger insert passes ``ignore_permissions`` because the scheduler runs it with no session
user, and an Accommodation Stock Ledger row is machine-written by definition: it records what the
period cost, and no operator files it or may edit it afterwards.
"""

from __future__ import annotations

import calendar
import frappe

_COST_TYPE_MAPPING = {
    "Rent": "annual_rent",
    "Electricity": "annual_electricity",
    "Water": "annual_water",
    "Cleaning Staff Salary": "annual_cleaning_staff",
    "Supervisor Salary": "annual_supervision",
    "Other": "annual_other_expenses",
}

_ROW_SAVEPOINT = "cost_row"


def _post_accommodation_ledger_row(
    *,
    posting_date,
    employee,
    assignment,
    building,
    project,
    cost_center,
    billed_to_supplier,
    ledger_type,
    annual_cost,
    capacity,
    days_in_year,
) -> None:
    """Insert ONE daily Operational-Memo Accommodation Ledger row from explicit
    params. Idempotent: an existing row for the (employee, posting_date,
    assignment, building, ledger_type) key is skipped. This is the ONLY writer of
    the daily accommodation-cost ledger row — both the batch allocator and the
    back-dating path route through it so the 18-key row and the
    daily-share rounding stay byte-identical.

    Callers OWN the try/except around this call: the batch allocator splits
    DuplicateEntryError from other errors; the back-dating path uses a single
    Exception guard. This helper deliberately does no exception handling.
    """
    from frappe.utils import flt

    daily_share = flt(flt(annual_cost / days_in_year, 5) / capacity, 5)

    if frappe.db.exists(
        "Accommodation Ledger",
        {
            "employee": employee,
            "posting_date": posting_date,
            "assignment": assignment,
            "building": building,
            "ledger_type": ledger_type,
        },
    ):
        return

    frappe.get_doc({
        "doctype": "Accommodation Ledger",
        "posting_date": posting_date,
        "employee": employee,
        "assignment": assignment,
        "building": building,
        "project": project,
        "cost_center": cost_center,
        "billed_to_supplier": billed_to_supplier,
        "ledger_type": ledger_type,
        "total_site_cost": annual_cost,
        "capacity_denominator": int(capacity),
        "employee_daily_share": daily_share,
        "posting_mode": "Operational Memo",
        "source_doctype": "Housing Assignment",
        "source_name": assignment,
        "allocation_basis": "Capacity",
        "allocation_period_start": posting_date,
        "allocation_period_end": posting_date,
    }).insert(ignore_permissions=True)


def daily_accommodation_cost_allocation() -> None:
    """Scheduler entry — fan daily accommodation cost allocation out PER BUILDING
    to the native ``long`` queue, so the scheduler worker is never blocked on a
    large dataset and buildings allocate in parallel. Buildings are discovered
    once; one idempotent job is enqueued per building (safe to retry).
    """
    from frappe.utils import today

    posting_date = today()
    buildings = frappe.get_all(
        "Housing Assignment",
        filters={
            "docstatus": 1,
            "check_out_date": ["is", "not set"],
            "building": ["is", "set"],
        },
        pluck="building",
        distinct=True,
    )
    for building in buildings:
        frappe.enqueue(
            "apex.habitat.tasks.cost.allocate_building_accommodation_cost",
            queue="long",
            timeout=3600,
            job_id=f"acc-cost-alloc::{building}::{posting_date}",
            deduplicate=True,
            enqueue_after_commit=True,
            building=building,
            posting_date=posting_date,
        )


def allocate_building_accommodation_cost(building, posting_date=None) -> None:
    """Allocate ONE building's daily accommodation costs to the Accommodation
    Ledger. Enqueued per building by ``daily_accommodation_cost_allocation`` (also
    directly callable). Idempotent — an existing ledger row for the
    (employee, posting_date, assignment, building, ledger_type) key is skipped, so
    retries and overlapping runs never duplicate.
    """
    from frappe.utils import today, flt

    posting_date = posting_date or today()
    logger = frappe.logger()

    year = int(posting_date[:4])
    days_in_year = 366 if calendar.isleap(year) else 365

    if not frappe.db.exists("Building", building):
        logger.warning(
            f"allocate_building_accommodation_cost: Building {building} not found. Skipping."
        )
        return
    building_doc = frappe.get_doc("Building", building)
    from apex.habitat.doctype.building.building import apply_active_lease
    apply_active_lease(building_doc)
    capacity = flt(building_doc.total_capacity)
    if capacity <= 0:
        logger.warning(
            f"allocate_building_accommodation_cost: Building {building} has invalid capacity {capacity}. Skipping."
        )
        return

    start = 0
    batch_size = 500
    while True:
        active_assignments = frappe.get_all(
            "Housing Assignment",
            filters={
                "docstatus": 1,
                "check_out_date": ["is", "not set"],
                "building": building,
            },
            fields=["name", "employee", "project", "cost_center", "billed_to_supplier"],
            limit_start=start,
            limit_page_length=batch_size,
        )
        if not active_assignments:
            break

        for asgn in active_assignments:
            if not asgn.employee:
                logger.warning(
                    f"allocate_building_accommodation_cost: Assignment {asgn.name} has no employee specified. Skipping."
                )
                continue

            for ledger_type, building_field in _COST_TYPE_MAPPING.items():
                annual_cost = flt(building_doc.get(building_field))
                if annual_cost <= 0:
                    continue

                frappe.db.savepoint(_ROW_SAVEPOINT)
                try:
                    _post_accommodation_ledger_row(
                        posting_date=posting_date,
                        employee=asgn.employee,
                        assignment=asgn.name,
                        building=building,
                        project=asgn.project,
                        cost_center=asgn.cost_center,
                        billed_to_supplier=asgn.billed_to_supplier,
                        ledger_type=ledger_type,
                        annual_cost=annual_cost,
                        capacity=capacity,
                        days_in_year=days_in_year,
                    )
                except frappe.exceptions.DuplicateEntryError:
                    frappe.db.rollback(save_point=_ROW_SAVEPOINT)
                except Exception as e:
                    frappe.db.rollback(save_point=_ROW_SAVEPOINT)
                    logger.error(
                        f"allocate_building_accommodation_cost: Failed to insert ledger row for assignment {asgn.name}, cost {ledger_type}: {e}"
                    )
                    frappe.log_error(
                        message=frappe.get_traceback(),
                        title=f"Cost allocation: ledger insert failed ({asgn.name}/{ledger_type})"[:140],
                    )

        start += batch_size


def backdate_assignment_cost(assignment_name, from_date, to_date=None) -> int:
    """Post the missed daily Operational-Memo accommodation-cost rows for ONE
    assignment over [from_date, to_date] (default to_date = today).

    Used when a Temporary Worker is linked to a real Employee (Batch 5): the days he
    was housed on a passport were skipped by the daily allocator (it skips an
    assignment with no employee), so they are back-dated to the now-linked Employee.
    Mirrors daily_accommodation_cost_allocation's per-assignment-per-date algorithm;
    idempotent (existence-guarded) and per-row error-isolated. Returns days processed.
    """
    from frappe.utils import today, getdate, add_days, flt

    to_date = to_date or today()
    asgn = frappe.db.get_value(
        "Housing Assignment",
        assignment_name,
        ["name", "employee", "building", "project", "cost_center", "billed_to_supplier"],
        as_dict=True,
    )
    if not asgn or not asgn.employee or not asgn.building:
        return 0
    try:
        building = frappe.get_doc("Building", asgn.building)
    except frappe.DoesNotExistError:
        return 0
    from apex.habitat.doctype.building.building import apply_active_lease
    apply_active_lease(building)
    capacity = flt(building.total_capacity)
    if capacity <= 0:
        return 0

    d = getdate(from_date)
    end = getdate(to_date)
    days = 0
    while d <= end:
        posting_date = str(d)
        days_in_year = 366 if calendar.isleap(d.year) else 365
        for ledger_type, building_field in _COST_TYPE_MAPPING.items():
            annual_cost = flt(building.get(building_field))
            if annual_cost <= 0:
                continue
            frappe.db.savepoint(_ROW_SAVEPOINT)
            try:
                _post_accommodation_ledger_row(
                    posting_date=posting_date,
                    employee=asgn.employee,
                    assignment=asgn.name,
                    building=asgn.building,
                    project=asgn.project,
                    cost_center=asgn.cost_center,
                    billed_to_supplier=asgn.billed_to_supplier,
                    ledger_type=ledger_type,
                    annual_cost=annual_cost,
                    capacity=capacity,
                    days_in_year=days_in_year,
                )
            except Exception:
                frappe.db.rollback(save_point=_ROW_SAVEPOINT)
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=f"Backdate cost insert failed ({asgn.name}/{ledger_type})"[:140],
                )
        days += 1
        d = getdate(add_days(d, 1))
    return days
