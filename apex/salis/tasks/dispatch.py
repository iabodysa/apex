# Copyright (c) 2026, afmcoltd

from __future__ import annotations

from datetime import date, datetime, time, timedelta

import frappe
from frappe.utils import get_time, getdate, today


HORIZON_DAYS = 14
SAVEPOINT = "masar_dispatch_assignment"


def scheduled_dates(start: date, end: date, weekdays: set[str]) -> list[date]:
    result = []
    current = start
    while current <= end:
        if current.strftime("%A") in weekdays:
            result.append(current)
        current += timedelta(days=1)
    return result


def planned_window(
    trip_date: date, start_time: time, end_time: time
) -> tuple[datetime, datetime]:
    planned_start = datetime.combine(trip_date, get_time(start_time))
    end_date = (
        trip_date
        if get_time(end_time) > get_time(start_time)
        else trip_date + timedelta(days=1)
    )
    return planned_start, datetime.combine(end_date, get_time(end_time))


def generation_key(route_assignment: str, trip_date: date) -> str:
    return f"{route_assignment}:{trip_date.isoformat()}"


def _driver_if_still_available(driver):
    """The assignment's driver, or ``None`` once he is no longer Active.

    A Route Assignment names its driver once and generates a trip from it every shift for
    the next fortnight. Stopping the driver refuses the stop while trips already name him,
    but nothing re-reads the assignment, so without this the generator writes his name back
    on tomorrow's trip the morning after he was stopped.

    The route still runs: the trip is created with no driver, which is what the assignment
    queue reads as needing one. Dropping the trip instead would strand the workers waiting
    on that route.
    """
    if not driver:
        return None
    if frappe.db.get_value("Salis Driver", driver, "status") != "Active":
        return None
    return driver


def generate_for_assignment(route_assignment, start_date=None, end_date=None):
    """Create the missing Dispatch Trips for ONE approved assignment's horizon.

    The assignment is loaded ``for_update`` so two overlapping runs cannot both read
    the same ``generated_through`` and both create the same day's trips —
    ``frappe.new_doc`` (frappe/__init__.py:1152) has no idempotency of its own, and a
    duplicate trip puts a second bus on one route.

    Returns how many were created; an assignment that is not submitted, approved and
    enabled creates nothing.
    """
    assignment = frappe.get_doc("Route Assignment", route_assignment, for_update=True)
    if not (
        assignment.docstatus == 1
        and assignment.status == "Approved"
        and assignment.enabled
    ):
        return 0

    shift = frappe.get_doc("Work Shift", assignment.work_shift)
    if not shift.is_active:
        return 0

    start = getdate(start_date or today())
    end = getdate(end_date or (start + timedelta(days=HORIZON_DAYS - 1)))
    start = max(start, getdate(assignment.starts_on))
    if assignment.generated_through:
        start = max(start, getdate(assignment.generated_through) + timedelta(days=1))
    if assignment.ends_on:
        end = min(end, getdate(assignment.ends_on))
    if start > end:
        return 0

    weekdays = {row.day_of_week for row in shift.applicable_days if row.day_of_week}
    driver = _driver_if_still_available(assignment.driver)
    created = 0
    for trip_date in scheduled_dates(start, end, weekdays):
        key = generation_key(assignment.name, trip_date)
        if frappe.db.exists("Dispatch Trip", {"generation_key": key}):
            continue
        planned_start, planned_end = planned_window(
            trip_date, shift.start_time, shift.end_time
        )
        trip = frappe.new_doc("Dispatch Trip")
        trip.update(
            {
                "trip_type": "Scheduled",
                "route_assignment": assignment.name,
                "route_template": assignment.route_template,
                "project": assignment.project,
                "shift_name": assignment.shift_name,
                "trip_date": trip_date,
                "planned_start": planned_start,
                "planned_end": planned_end,
                "vehicle": assignment.vehicle,
                "driver": driver,
                "status": "Planned",
                "generation_key": key,
            }
        )
        try:
            trip.insert()
        except frappe.DuplicateEntryError:
            continue
        created += 1

    assignment.db_set("generated_through", end, update_modified=False)
    return created


def generate_recurring_trips(start_date=None, days=HORIZON_DAYS):
    """Generate the coming horizon's trips for every approved Route Assignment.

    ``frappe.db.savepoint`` / ``rollback`` (frappe/database/database.py:1203, :1186)
    isolate each unit. The one thing a plain try/except cannot do is undo a PARTIAL
    write: a row that fails midway leaves what it already inserted, and the next unit
    inherits it. The failure goes to the Error Log through ``frappe.get_traceback``
    and the loop carries on.

    One bad assignment must not cost the whole horizon: without the per-assignment
    point, a single malformed schedule leaves every fleet with no trips tomorrow.
    """
    start = getdate(start_date or today())
    end = start + timedelta(days=days - 1)
    assignments = frappe.get_all(
        "Route Assignment",
        filters={
            "docstatus": 1,
            "status": "Approved",
            "enabled": 1,
            "starts_on": ["<=", end],
        },
        or_filters=[["ends_on", "is", "not set"], ["ends_on", ">=", start]],
        pluck="name",
    )
    created = 0
    for name in assignments:
        frappe.db.savepoint(SAVEPOINT)
        try:
            created += generate_for_assignment(name, start, end)
        except Exception:
            frappe.db.rollback(save_point=SAVEPOINT)
            frappe.log_error(
                title="Recurring dispatch generation failed",
                message=frappe.get_traceback(with_context=True),
            )
    return created


def daily_dispatch_trip_generation():
    return generate_recurring_trips()
