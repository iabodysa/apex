# Copyright (c) 2026, Apex contributors
"""Fleet OS supervisor dashboard API (read + live operations).

Backs the ``/fleet-os`` www page, which is the fleet supervisor's single-screen
dashboard. The page is a faithful copy of the supervisor's own design; this
module replaces the design's embedded JSON with LIVE Salis data and routes its
operations to the real DocTypes.

This module is the endpoint surface: every whitelisted method the dashboard calls
lives here under the dotted path its bundle already holds. The board READ — which
fields make a vehicle, how a driver appears on a card, how an incident becomes a
stolen flag — lives in :mod:`apex.salis.api.fleet_os_board`, so changing what the
screen shows is one edit in one file.

The `fleet-operations` feature calls this module. The fleet representative feature
uses `apex.salis.api.fleet_employee` instead.

Every endpoint is permission-gated on ``Salis Vehicle`` and project-scoped
server-side through the SAME ``_permitted_projects`` resolver the dispatch
board, fleet control board and the list-view ``permission_query_conditions``
use, so the dashboard never shows (or mutates) a project a scoped supervisor
could not already see. Writes reuse the existing controllers (Vehicle
Assignment, Vehicle Suspension, Vehicle Incident) — no parallel logic.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import getdate, today

from apex.salis.api.dispatch_board import _permitted_projects
from apex.salis.api.fleet_os_board import build_board, driver_pii_visible
from apex.salis.doctype.vehicle_incident.vehicle_incident import close_incident_internal
from apex.salis.utils import (
    close_open_stop,
    lock_vehicle,
    normalize_plate,
    reassign_vehicle_driver,
)


def _publish_fleet_update(plate: str | None = None, action: str | None = None) -> None:
    """Signal the /fleet-os board to refetch ahead of its poll. Routed to the Salis
    Vehicle doctype room; the socket server delivers only to recipients with read
    permission, so scope is honoured without extra filtering. after_commit so
    subscribers refetch committed state. The payload is advisory only — the SPA
    refetches via get_fleet_os, it does not trust the message body."""
    frappe.publish_realtime(
        "fleet_update",
        {"plate": plate, "action": action},
        doctype="Salis Vehicle",
        after_commit=True,
    )


_STOP_REASON_MAP = {
    "maintenance": "Maintenance",
    "rental return": "Rental Return",
    "rental": "Rental Return",
    "return": "Rental Return",
}


def _resolve_plate(plate: str, ptype: str = "write") -> str:
    """Resolve a plate string from the dashboard to a Salis Vehicle name,
    permission-checked. Matches plate_number, then plate_normalized, then name.
    Raises if not found or not permitted. ``ptype`` is "write" for the action
    endpoints (the default) and "read" for read-only ones (the timeline).
    """
    if not plate:
        frappe.throw(_("Plate is required."))
    name = frappe.db.get_value("Salis Vehicle", {"plate_number": plate}, "name")
    if not name:
        normalized = normalize_plate(plate)
        name = frappe.db.get_value("Salis Vehicle", {"plate_normalized": normalized}, "name")
    if not name and frappe.db.exists("Salis Vehicle", {"name": plate}):
        name = plate
    if not name:
        frappe.throw(_("Vehicle {0} not found.").format(plate))
    frappe.has_permission("Salis Vehicle", ptype, doc=name, throw=True)
    return name


def _resolve_driver_id(driver_id: str) -> str:
    """Resolve the dashboard's EXTERNAL fleet identifier (Salis Driver.driver_id)
    to a Salis Driver name, refusing anything that resolves to nothing.
    """
    if not driver_id:
        frappe.throw(_("Driver is required."))
    driver = frappe.db.get_value("Salis Driver", {"driver_id": driver_id}, "name")
    if not driver and frappe.db.exists("Salis Driver", {"name": driver_id}):
        driver = driver_id
    if not driver:
        frappe.throw(_("Driver {0} not found.").format(driver_id))
    return driver


@frappe.whitelist()
def get_fleet_os():
    """Return the full fleet in the design's exact shape (a ``vehicles`` list).

    Project scope is enforced server-side: a scoped user with no permitted
    project gets an empty list. N+1-free (three bounded queries + the category
    fuel lookup).

    An empty result carries a typed ``reason`` so the page can tell the two apart:
    ``scope_empty`` (the user is scoped to no project — an access gap) vs
    ``data_empty`` (the permitted fleet is genuinely empty). A non-empty result
    has ``reason: None``. Filtered-empty stays a client concern (the page knows
    its own active filters).
    """
    frappe.has_permission("Salis Vehicle", "read", throw=True)
    result = build_board()
    can_write = bool(frappe.has_permission("Salis Vehicle", "write"))
    for vehicle in result.get("vehicles", []):
        status = vehicle.get("vehicle_status")
        vehicle["capabilities"] = {
            "stop": {"allowed": can_write and status in ("assigned", "available"), "reason": _("Only an authorised user can stop an active vehicle.")},
            "workshopIn": {"allowed": can_write and status != "workshop", "reason": _("Vehicle is already in the workshop or you cannot update it.")},
            "workshopOut": {"allowed": can_write and status == "workshop", "reason": _("Vehicle has no open workshop visit or you cannot update it.")},
            "recover": {"allowed": can_write and status == "stopped", "reason": _("Only an authorised user can return a stopped vehicle to service.")},
        }
    return result


def _queue_scope(project=None):
    """Return a project filter that can only narrow the caller's User Permissions."""
    unscoped, projects = _permitted_projects()
    if project:
        if unscoped:
            return [project]
        return [project] if project in (projects or []) else []
    return None if unscoped else list(projects or [])


def _project_queue(doctype, fields, project=None, filters=None, order_by="modified desc", limit=100):
    frappe.has_permission(doctype, "read", throw=True)
    projects = _queue_scope(project)
    if projects == []:
        return []
    scoped_filters = dict(filters or {})
    if projects is not None:
        scoped_filters["project"] = ["in", projects]
    return frappe.get_list(
        doctype,
        filters=scoped_filters,
        fields=fields,
        order_by=order_by,
        limit_page_length=limit,
    )


@frappe.whitelist()
def get_assignment_queue(project=None):
    return _project_queue(
        "Vehicle Assignment",
        ["name", "vehicle", "driver", "project", "start_date", "end_date", "status", "docstatus"],
        project=project,
        filters={"docstatus": ["<", 2]},
        order_by="start_date desc, creation desc",
    )


def _handover_queue(direction, project=None):
    projects = _queue_scope(project)
    if projects == []:
        return []
    vehicle_filters = {"project": ["in", projects]} if projects is not None else {}
    vehicles = frappe.get_list("Salis Vehicle", filters=vehicle_filters, pluck="name", limit_page_length=0)
    if not vehicles:
        return []
    return frappe.get_list(
        "Vehicle Handover",
        filters={"vehicle": ["in", vehicles], "direction": direction, "docstatus": ["<", 2]},
        fields=["name", "direction", "vehicle", "from_driver", "to_driver", "handover_date", "discrepancy_status", "docstatus"],
        order_by="handover_date desc, creation desc",
        limit_page_length=100,
    )


@frappe.whitelist()
def get_handover_queue(project=None):
    return _handover_queue("Receipt", project)


@frappe.whitelist()
def get_return_queue(project=None):
    return _handover_queue("Return", project)


@frappe.whitelist()
def get_incident_queue(project=None):
    projects = _queue_scope(project)
    if projects == []:
        return []
    driver_filters = {"project": ["in", projects]} if projects is not None else {}
    drivers = frappe.get_list("Salis Driver", filters=driver_filters, pluck="name", limit_page_length=0)
    if not drivers:
        return []
    return frappe.get_list(
        "Vehicle Incident",
        filters={"driver": ["in", drivers], "docstatus": ["<", 2]},
        fields=["name", "incident_type", "vehicle", "driver", "incident_date", "location", "description", "status"],
        order_by="incident_date desc, creation desc",
        limit_page_length=100,
    )


@frappe.whitelist()
def get_incident_detail(name):
    doc = frappe.get_doc("Vehicle Incident", name)
    frappe.has_permission("Vehicle Incident", "read", doc=doc, throw=True)
    return doc.as_dict(no_nulls=False)


@frappe.whitelist()
def get_problem_queue(project=None):
    return _project_queue(
        "Issue",
        ["name", "subject", "description", "priority", "status", "project", "custom_driver", "modified"],
        project=project,
        filters={"issue_type": "Complaint"},
    )


@frappe.whitelist()
def get_problem_detail(name):
    doc = frappe.get_doc("Issue", name)
    frappe.has_permission("Issue", "read", doc=doc, throw=True)
    if doc.issue_type != "Complaint":
        frappe.throw(_("Problem not found."), frappe.DoesNotExistError)
    result = doc.as_dict(no_nulls=False)
    result["communications"] = frappe.get_all(
        "Communication",
        filters={"reference_doctype": "Issue", "reference_name": name},
        fields=["name", "sender", "content", "communication_date"],
        order_by="communication_date asc, creation asc",
        limit_page_length=100,
    )
    return result


@frappe.whitelist()
def get_operations_overview(project=None):
    vehicles = get_fleet_os().get("vehicles", [])
    assignments = get_assignment_queue(project)
    fuel = get_pending_fuel_requests_for_overview(project)
    incidents = get_incident_queue(project)
    return {"summary": {
        "vehicles": len(vehicles),
        "assignments": sum(1 for row in assignments if row.status == "Active"),
        "fuel_pending": len(fuel),
        "incidents_open": sum(1 for row in incidents if row.status in ("Open", "Under Review")),
    }}


def get_pending_fuel_requests_for_overview(project=None):
    from apex.salis.api.fuel_console import get_pending_fuel_requests

    return get_pending_fuel_requests(project)


@frappe.whitelist()
def get_vehicle_timeline(plate):
    """Merged per-vehicle audit timeline for the /fleet-os panel Log tab.

    One descending feed of the vehicle's assignments, stops, incidents and
    Fleet Supervisor queue entries. Read-permission- and project-scope-gated through the SAME
    ``_resolve_plate`` resolver the actions use (in read mode), and the
    permlevel-1 PII gate blanks the driver id on assignment rows for a role
    without it. N+1-free: one bounded ``get_all`` per source, merged in Python.
    """
    vehicle = _resolve_plate(plate, ptype="read")
    show_pii = driver_pii_visible()

    events: list[dict] = []

    for a in frappe.get_all(
        "Vehicle Assignment",
        filters={"vehicle": vehicle},
        fields=["name", "driver", "start_date", "end_date", "status", "docstatus"],
        order_by="start_date desc",
        limit_page_length=0,
    ):
        events.append({
            "kind": "assignment",
            "date": str(a.start_date or ""),
            "title": _("Driver assigned"),
            "ref_doctype": "Vehicle Assignment",
            "ref_name": a.name,
            "driver": (a.driver or "") if show_pii else "",
            "status": a.status or "",
            "end_date": str(a.end_date or ""),
        })

    for s in frappe.get_all(
        "Vehicle Suspension",
        filters={"vehicle": vehicle, "docstatus": ["<", 2]},
        fields=["name", "stop_reason", "stop_date", "return_date", "notes"],
        order_by="stop_date desc",
        limit_page_length=0,
    ):
        events.append({
            "kind": "stop",
            "date": str(s.stop_date or ""),
            "title": _(s.stop_reason) if s.stop_reason else _("Stop"),
            "ref_doctype": "Vehicle Suspension",
            "ref_name": s.name,
            "return_date": str(s.return_date or ""),
            "notes": s.notes or "",
        })

    for inc in frappe.get_all(
        "Vehicle Incident",
        filters={"vehicle": vehicle, "docstatus": ["<", 2]},
        fields=["name", "incident_type", "incident_date", "status", "location"],
        order_by="incident_date desc, incident_time desc",
        limit_page_length=0,
    ):
        events.append({
            "kind": "incident",
            "date": str(inc.incident_date or ""),
            "title": _(inc.incident_type) if inc.incident_type else _("Incident"),
            "ref_doctype": "Vehicle Incident",
            "ref_name": inc.name,
            "status": inc.status or "",
            "location": inc.location or "",
        })

    from apex.salis.api.assignment_queue import queue_events_for_vehicle

    for q in queue_events_for_vehicle(vehicle, ("Open", "Overdue", "Closed"), 100):
        events.append({
            "kind": "alert",
            "date": str(q.raised_on or ""),
            "title": _(q.alert_type),
            "ref_doctype": q.reference_type,
            "ref_name": q.reference_name,
            "severity": q.severity or "",
            "status": q.status or "",
            "message": q.message or "",
        })

    events.sort(key=lambda e: e.get("date") or "", reverse=True)
    return {"events": events}


@frappe.whitelist(methods=["POST"])
def reassign(plate, driver_id, date=None):
    """Assign a driver to a vehicle by creating a submitted Vehicle Assignment.

    ``driver_id`` is the EXTERNAL fleet identifier (Salis Driver.driver_id), as
    the dashboard carries it; ``_resolve_driver_id`` resolves it to the Salis
    Driver name. The Vehicle Assignment controller handles the link side; we also
    set the vehicle's current_driver and the driver's current_vehicle so the live
    state matches immediately (the assignment alone does not mutate those).
    """
    vehicle = _resolve_plate(plate)
    driver = _resolve_driver_id(driver_id)
    frappe.has_permission("Salis Driver", "write", doc=driver, throw=True)

    assignment = reassign_vehicle_driver(vehicle, driver, date)
    _publish_fleet_update(plate, "reassign")
    return {"ok": True, "assignment": assignment}


@frappe.whitelist(methods=["POST"])
def stop_vehicle(plate, reason=None):
    """Stop a vehicle and release its driver by submitting a Vehicle Suspension.

    Vehicle Suspension.on_submit flips Salis Vehicle.status to "Stopped". The free-text
    reason is mapped to the nearest no-evidence Select option (default "Other")
    so the submit never trips the evidence gate. The current assignment is ended
    and the driver link cleared to match the released state.
    """
    vehicle = _resolve_plate(plate)
    lock_vehicle(vehicle)
    stop_reason = _STOP_REASON_MAP.get((reason or "").strip().lower(), "Other")

    current_driver = frappe.db.get_value("Salis Vehicle", vehicle, "current_driver")

    doc = frappe.get_doc({
        "doctype": "Vehicle Suspension",
        "vehicle": vehicle,
        "stop_reason": stop_reason,
        "stop_date": getdate(today()),
        "notes": (reason or ""),
    })
    doc.insert()
    doc.submit()

    if current_driver:
        for r in frappe.get_all(
            "Vehicle Assignment",
            filters={"vehicle": vehicle, "status": "Active", "docstatus": 1},
            fields=["name"],
        ):
            frappe.db.set_value("Vehicle Assignment", r.name, {"status": "Ended", "end_date": getdate(today())})
        frappe.db.set_value("Salis Vehicle", vehicle, "current_driver", None)
        frappe.db.set_value("Salis Driver", current_driver, "current_vehicle", None)
    _publish_fleet_update(plate, "stop")
    return {"ok": True, "stop": doc.name}


@frappe.whitelist(methods=["POST"])
def workshop_in(plate, expected_return=None, notes=None):
    """Send a vehicle to the workshop via a submittable Maintenance Vehicle Suspension.

    Mirrors stop_vehicle/report_theft/reassign: the workshop event is now an
    audited submitted record, not a bare status flip. The Vehicle Suspension controller
    (reason Maintenance) captures previous_status, writes the timeline note/comment
    and flips the vehicle to "Stopped"; we then set "Under Maintenance" so the
    board's workshop lane stays distinct from a plain stop (both states are the
    open-workshop set in tasks._overstay_stops, so the overstay rule still fires).

    The stop's return_date is the ACTUAL workshop-exit date (empty == still in the
    workshop, the invariant _overstay_stops/release rely on), so an EXPECTED return
    is recorded in the notes rather than pre-filling that field.
    """
    vehicle = _resolve_plate(plate)
    lock_vehicle(vehicle)

    note = (notes or "").strip()
    if expected_return:
        expected = _("Expected return: {0}").format(getdate(expected_return))
        note = f"{note}\n{expected}".strip() if note else expected

    doc = frappe.get_doc({
        "doctype": "Vehicle Suspension",
        "vehicle": vehicle,
        "stop_reason": "Maintenance",
        "stop_date": getdate(today()),
        "notes": note,
    })
    doc.insert()
    doc.submit()

    frappe.db.set_value("Salis Vehicle", vehicle, "status", "Under Maintenance")
    _publish_fleet_update(plate, "workshop_in")
    return {"ok": True, "stop": doc.name}


@frappe.whitelist(methods=["POST"])
def workshop_out(plate):
    """Return a vehicle from the workshop by closing its open Maintenance stop.

    Mirrors operations_control.release_vehicle: stamp the workshop-exit fields on
    the open submitted Maintenance Vehicle Suspension and cancel it, so the cancel leaves
    its own audit note. on_cancel only auto-restores when the vehicle still reads
    "Stopped"; since workshop_in parks it at "Under Maintenance", we restore the
    stop's captured previous_status here. Throws when there is no open workshop stop.
    """
    vehicle = _resolve_plate(plate)
    lock_vehicle(vehicle)

    stop = frappe.db.get_value(
        "Vehicle Suspension",
        {"vehicle": vehicle, "stop_reason": "Maintenance", "docstatus": 1,
         "return_date": ["is", "not set"]},
        ["name", "previous_status"],
        as_dict=True,
        order_by="creation desc",
    )
    if not stop:
        frappe.throw(_("This vehicle has no open workshop stop to return."))

    close_open_stop(stop.name)
    if frappe.db.get_value("Salis Vehicle", vehicle, "status") == "Under Maintenance":
        frappe.db.set_value("Salis Vehicle", vehicle, "status", stop.previous_status or "Active")
    _publish_fleet_update(plate, "workshop_out")
    return {"ok": True, "stop": stop.name}


def _close_open_suspension(vehicle):
    """Close whatever submitted Vehicle Suspension still holds this vehicle.

    Returning a vehicle to service is the act that ends its stop, so the stop record
    has to end with it — otherwise the vehicle reads Active while a submitted
    suspension stays open behind it, and the two never agree again. Uses the shared
    ``close_open_stop``, which stamps the audit fields and cancels through the native
    lifecycle rather than poking the vehicle a second time."""
    for r in frappe.get_all(
        "Vehicle Suspension",
        filters={"vehicle": vehicle, "docstatus": 1, "released_on": ["is", "not set"]},
        pluck="name",
    ):
        close_open_stop(r)


@frappe.whitelist(methods=["POST"])
def recover(plate):
    """Recover a stopped/stolen vehicle back to service.

    When the vehicle has an open Theft Vehicle Incident on record, close it in the
    same transaction and restore the state it captured at report time
    (``previous_driver`` / ``previous_status``) — so a recovered vehicle is
    not left with a Theft incident Open forever. With no theft on record (a plain
    stop), recover simply returns the vehicle to Active.
    """
    vehicle = _resolve_plate(plate)

    incident = frappe.db.get_value(
        "Vehicle Incident",
        {"vehicle": vehicle, "incident_type": "Theft", "docstatus": 1,
         "status": ["in", ("Open", "Under Review")]},
        ["name", "previous_driver", "previous_status"],
        as_dict=True,
        order_by="creation desc",
    )
    if incident:
        close_incident_internal(
            incident.name,
            "Vehicle recovered through Fleet OS.",
            check_permission=False,
        )

    lock_vehicle(vehicle)
    _close_open_suspension(vehicle)

    if not incident:
        frappe.db.set_value("Salis Vehicle", vehicle, "status", "Active")
        _publish_fleet_update(plate, "recover")
        return {"ok": True}

    if incident.previous_driver and not frappe.db.get_value(
        "Salis Vehicle", vehicle, "current_driver"
    ):
        frappe.db.set_value("Salis Vehicle", vehicle, "current_driver", incident.previous_driver)
        frappe.db.set_value("Salis Driver", incident.previous_driver, "current_vehicle", vehicle)

    frappe.db.set_value(
        "Salis Vehicle", vehicle, "status", incident.previous_status or "Active"
    )
    _publish_fleet_update(plate, "recover")
    return {"ok": True, "incident": incident.name}
