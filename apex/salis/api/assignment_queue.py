# Copyright (c) 2026, AFMCO and contributors
"""Assignment-queue reader for the operations board, the /fleet-os drawer and the
vehicle timelines.

A condition about a document ASSIGNS that document to the Fleet Supervisor queue
(the ToDo carries reference_type/reference_name), and a non-document condition
notifies the role. The board and the drawer still speak the row shape of the
retired alert DocType, and their built JS predates its retirement — so this
module reads the open assignment queue and renders it in that exact shape.
Severity round-trips through the ToDo priority the writers set; ``alert_type``
is derived from the reference DocType for display only — it is never a dedupe or
filter key, so the retired fragile text-matching dedupe cannot come back through
here.
"""

from __future__ import annotations

import frappe

from apex.salis.tasks.common import PRIORITY_TO_SEVERITY, QUEUE_DOCTYPES

OPEN_TODO_STATUSES = ("Open", "Overdue")

_REFTYPE_ALERT_TYPE = {
    "Vehicle Suspension": "Maintenance Overdue",
    "Fuel Quota": "Excessive Topup",
    "Rental Office": "Unsettled Rental",
    "Salis Driver": "Supervisor Delay",
}


def _alert_type_for(reference_type: str, description: str | None) -> str:
    """Display label for a queue row. Salis Vehicle is queued by two watchers
    (idle and compliance), so its label alone is read off the description the
    writer set — display only, never matched against."""
    if reference_type in _REFTYPE_ALERT_TYPE:
        return _REFTYPE_ALERT_TYPE[reference_type]
    return "License Expiry" if "compliance" in (description or "").lower() else "Idle Vehicle"


def _vehicle_driver_refs(groups: list[dict]) -> None:
    """Stamp ``vehicle``/``driver`` onto each grouped queue row from its reference
    document, batched per DocType (no per-row queries)."""
    names_by_type: dict[str, list[str]] = {}
    for g in groups:
        names_by_type.setdefault(g["reference_type"], []).append(g["reference_name"])

    vehicle_of: dict[tuple[str, str], str | None] = {}
    driver_of: dict[tuple[str, str], str | None] = {}
    for doctype, fields in (("Vehicle Suspension", ["vehicle"]), ("Fuel Quota", ["vehicle", "driver"])):
        for r in (
            frappe.get_all(
                doctype,
                filters={"name": ["in", names_by_type[doctype]]},
                fields=["name"] + fields,
            )
            if names_by_type.get(doctype)
            else []
        ):
            vehicle_of[(doctype, r.name)] = r.get("vehicle")
            driver_of[(doctype, r.name)] = r.get("driver")

    for g in groups:
        key = (g["reference_type"], g["reference_name"])
        if g["reference_type"] == "Salis Vehicle":
            g["vehicle"], g["driver"] = g["reference_name"], None
        elif g["reference_type"] == "Salis Driver":
            g["vehicle"], g["driver"] = None, g["reference_name"]
        else:
            g["vehicle"] = vehicle_of.get(key)
            g["driver"] = driver_of.get(key)


def open_queue_rows() -> list:
    """The open Fleet Supervisor queue rendered as alert-shaped rows.

    One row per queued DOCUMENT (a role assignment is one ToDo per holder, so the
    holders collapse into the row's assignee list). The row ``name`` is the oldest
    ToDo's name — an id the action endpoints resolve back to the reference
    document. Caller applies its own scope filtering.
    """
    todos = frappe.get_all(
        "ToDo",
        filters={
            "reference_type": ["in", list(QUEUE_DOCTYPES)],
            "reference_name": ["is", "set"],
            "status": ["in", list(OPEN_TODO_STATUSES)],
        },
        fields=[
            "name", "reference_type", "reference_name", "description",
            "priority", "creation", "allocated_to",
        ],
        order_by="creation asc",
        limit_page_length=0,
    )

    grouped: dict[tuple[str, str], dict] = {}
    for t in todos:
        key = (t.reference_type, t.reference_name)
        g = grouped.get(key)
        if g is None:
            g = grouped[key] = {
                "name": t.name,
                "reference_type": t.reference_type,
                "reference_name": t.reference_name,
                "description": t.description,
                "priority": t.priority,
                "creation": t.creation,
                "allocated": [],
            }
        if t.allocated_to and t.allocated_to not in g["allocated"]:
            g["allocated"].append(t.allocated_to)

    groups = list(grouped.values())
    _vehicle_driver_refs(groups)

    rows = []
    for g in groups:
        rows.append(
            frappe._dict(
                name=g["name"],
                alert_type=_alert_type_for(g["reference_type"], g["description"]),
                severity=PRIORITY_TO_SEVERITY.get(g["priority"], "Warning"),
                status="Open",
                vehicle=g["vehicle"],
                driver=g["driver"],
                message=g["description"],
                raised_on=g["creation"],
                snooze_until=None,
                _assign=frappe.as_json(g["allocated"]),
            )
        )
    return rows


def queue_ref(name: str):
    """The (reference_type, reference_name) behind a queue-backed row id, or None
    when ``name`` is not a queue ToDo."""
    row = frappe.db.get_value(
        "ToDo", name, ["reference_type", "reference_name"], as_dict=True
    )
    if row and row.reference_type in QUEUE_DOCTYPES and row.reference_name:
        return row
    return None


def queue_events_for_vehicle(vehicle: str, statuses, limit: int) -> list:
    """Queue history for one vehicle as alert-shaped events, for the timelines.

    Covers the references that anchor to a vehicle: the Salis Vehicle itself, its
    Vehicle Suspensions and its Fuel Quotas. ``statuses`` picks open and/or closed
    ToDos; closed rows are the resolved half the legacy timeline read from
    ``status = Resolved`` alert rows.
    """
    refs = {("Salis Vehicle", vehicle)}
    for doctype in ("Vehicle Suspension", "Fuel Quota"):
        for n in frappe.get_all(
            doctype, filters={"vehicle": vehicle}, pluck="name", limit_page_length=0
        ):
            refs.add((doctype, n))

    todos = frappe.get_all(
        "ToDo",
        filters={
            "reference_type": ["in", ["Salis Vehicle", "Vehicle Suspension", "Fuel Quota"]],
            "reference_name": ["in", [r[1] for r in refs]],
            "status": ["in", list(statuses)],
        },
        fields=["name", "reference_type", "reference_name", "description",
                "priority", "creation", "modified", "status"],
        order_by="modified desc",
        limit_page_length=limit,
    )
    events = []
    for t in todos:
        if (t.reference_type, t.reference_name) not in refs:
            continue
        events.append(
            frappe._dict(
                name=t.name,
                alert_type=_alert_type_for(t.reference_type, t.description),
                severity=PRIORITY_TO_SEVERITY.get(t.priority, "Warning"),
                status="Resolved" if t.status == "Closed" else "Open",
                message=t.description,
                raised_on=t.creation,
                closed_on=t.modified,
                reference_type=t.reference_type,
                reference_name=t.reference_name,
            )
        )
    return events
