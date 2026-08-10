# Copyright (c) 2026, afmcoltd
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

Route trace (NOT ``/fleet`` — that is the unrelated employee self-service page,
whose bundle calls ``apex.salis.api.fleet_employee`` only): hooks.py tile
"apex-fleet-os" -> ``/fleet-os`` -> ``www/fleet-os.html`` ->
``/assets/apex/fleet_os_portal/assets/index.js``, built from ``frontend/fleet_os``
(``vite.config.js`` name="fleet_os_portal"), whose ``useFleetBoard`` /
``useFleetActions`` / ``useDriverAssignment`` composables call this module.

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
from apex.salis.utils import (
    add_timeline_note,
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
    return build_board()


@frappe.whitelist()
def search_drivers(q=None, limit=20):
    """Typeahead over Salis Driver backing the reassign picker.

    Same gates as :func:`get_fleet_os`: read permission on Salis Driver, project
    scope via ``_permitted_projects`` (a scoped supervisor only finds drivers on
    a permitted-project vehicle or with no vehicle yet), and the permlevel-1 PII
    gate on ``driver_id``/``phone`` — blanked for a role without it.

    Each row carries the canonical Salis Driver ``name``; the picker binds THAT
    (not free-typed text) so reassign resolves a real, permitted driver and a
    typo can no longer silently mis-assign a vehicle.
    """
    frappe.has_permission("Salis Driver", "read", throw=True)
    show_pii = driver_pii_visible()
    unscoped, projects = _permitted_projects()
    if not unscoped and not projects:
        return []

    try:
        limit = max(1, min(int(limit), 50))
    except (TypeError, ValueError):
        limit = 20

    filters = {"status": "Active"}
    or_filters = None
    term = (q or "").strip()
    if term:
        like = f"%{term}%"
        or_filters = {"full_name": ["like", like]}
        if show_pii:
            or_filters["driver_id"] = ["like", like]

    rows = frappe.get_all(
        "Salis Driver",
        filters=filters,
        or_filters=or_filters,
        fields=["name", "full_name", "driver_id", "phone", "current_vehicle", "project"],
        order_by="full_name asc",
        limit_page_length=limit * 3 if not unscoped else limit,
    )

    if not unscoped:
        veh_names = {r.current_vehicle for r in rows if r.get("current_vehicle")}
        permitted_veh = set()
        if veh_names:
            permitted_veh = {
                v.name
                for v in frappe.get_all(
                    "Salis Vehicle",
                    filters={"name": ["in", list(veh_names)], "project": ["in", projects]},
                    fields=["name"],
                )
            }
        rows = [
            r for r in rows
            if not r.get("current_vehicle") or r.current_vehicle in permitted_veh
        ][:limit]

    return [
        {
            "name": r.name,
            "full_name": r.full_name or "",
            "driver_id": (r.driver_id or "") if show_pii else "",
            "phone": (r.phone or "") if show_pii else "",
            "current_vehicle": r.current_vehicle or "",
        }
        for r in rows
    ]


@frappe.whitelist()
def get_status_meta():
    """Return the Salis Vehicle ``status`` Select options as label/value pairs.

    Server-drives the SPA's status chips so the front-end stops hand-keeping a
    label map that drifts from the DocType Select. ``value`` is the canonical
    English option (the stored value); ``label`` is the translated display
    string. Read-gated like the rest of the dashboard.
    """
    frappe.has_permission("Salis Vehicle", "read", throw=True)
    field = frappe.get_meta("Salis Vehicle").get_field("status")
    options = [o.strip() for o in (field.options or "").split("\n") if o.strip()] if field else []
    return {"statuses": [{"value": o, "label": _(o)} for o in options]}


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
def create_handover(plate, driver_id, date=None, odometer=None, checklist_template=None, condition_notes=None):
    """Create an OPTIONAL DRAFT Vehicle Handover for a just-reassigned vehicle.

    Called by /fleet-os AFTER reassign succeeds, only when the supervisor ticked the
    optional capture box. Reuses the native Vehicle Handover DocType/controller —
    no parallel handover logic. It is left as a DRAFT (insert only, never submit):
    the controller requires signed evidence before submit, so a manager later
    attaches it and submits via Desk (where the checklist UI + print format live).

    ``to_driver`` is the just-assigned driver, resolved through the SAME
    ``_resolve_driver_id`` reassign used so the two cannot disagree about which
    driver the identifier names; ``from_driver`` is the previous driver, read from
    the most recent Ended assignment reassign left behind. With no prior driver (a
    first-ever assignment) there is no custody to transfer, so no handover is
    drafted — the caller shows that as a benign notice. A checklist template, when
    given, is loaded via the existing template loader.
    """
    vehicle = _resolve_plate(plate)
    to_driver = _resolve_driver_id(driver_id)
    frappe.has_permission("Vehicle Handover", "create", throw=True)

    prev = frappe.get_all(
        "Vehicle Assignment",
        filters={"vehicle": vehicle, "status": "Ended", "driver": ["!=", to_driver], "docstatus": 1},
        fields=["driver"],
        order_by="end_date desc, creation desc",
        limit_page_length=1,
    )
    from_driver = prev[0].driver if prev else None

    if not from_driver:
        return {"ok": True, "handover": None, "skipped": "no_prior_driver"}

    doc = frappe.get_doc({
        "doctype": "Vehicle Handover",
        "vehicle": vehicle,
        "from_driver": from_driver,
        "to_driver": to_driver,
        "handover_date": getdate(date) if date else getdate(today()),
        "condition_notes": condition_notes or "",
    })
    if odometer not in (None, ""):
        try:
            doc.odometer_reading = int(odometer)
        except (TypeError, ValueError):
            pass
    doc.insert()

    if checklist_template and frappe.db.exists(
        "Vehicle Handover Checklist Template", {"name": checklist_template}
    ):
        from apex.salis.doctype.vehicle_handover_checklist_template.vehicle_handover_checklist_template import (
            load_template_into_doc,
        )

        load_template_into_doc(doc.name, checklist_template)

    return {"ok": True, "handover": doc.name}


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
def report_theft(plate, location=None, report_number=None):
    """Report a vehicle stolen by submitting a Theft Vehicle Incident.

    Vehicle Incident.on_submit (Theft) flips Salis Vehicle.status to "Stopped",
    nulls current_driver, and clears the ex-driver's current_vehicle — the
    controller owns that flow, so we only build and submit the incident.
    """
    vehicle = _resolve_plate(plate)
    doc = frappe.get_doc({
        "doctype": "Vehicle Incident",
        "incident_type": "Theft",
        "vehicle": vehicle,
        "incident_date": getdate(today()),
        "location": (location or ""),
        "report_number": (report_number or ""),
        "description": _("Reported stolen from the Fleet OS dashboard."),
    })
    doc.insert()
    doc.submit()
    _publish_fleet_update(plate, "theft")
    return {"ok": True, "incident": doc.name}


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


BULK_PLATE_LIMIT = 50


def _coerce_plates(plates) -> list[str]:
    """Normalize the plates param (a JSON array over HTTP, or a real list) to a
    de-duplicated, order-preserving list of non-empty plate strings.

    Capped at ``BULK_PLATE_LIMIT``. Every plate in a batch takes a row lock through
    ``lock_vehicle`` and a ``tabSeries`` lock that is held until the whole REQUEST
    commits, so an uncapped selection does not merely run long — it holds the series
    lock the entire time and blocks every other writer that needs a new name. The
    operator is told the limit and how many they selected, so the answer is to send
    fewer rather than to guess.
    """
    parsed = frappe.parse_json(plates) if isinstance(plates, str) else plates
    if not isinstance(parsed, (list, tuple)):
        frappe.throw(_("Select at least one vehicle."))
    seen: dict[str, None] = {}
    for p in parsed:
        key = str(p).strip()
        if key:
            seen.setdefault(key, None)
    if not seen:
        frappe.throw(_("Select at least one vehicle."))
    if len(seen) > BULK_PLATE_LIMIT:
        frappe.throw(
            _("Apply to at most {0} vehicles at a time. You selected {1}.").format(
                BULK_PLATE_LIMIT, len(seen)
            )
        )
    return list(seen)


def _bulk_apply(plates, action) -> dict:
    """Run a single-vehicle fleet action over many plates, isolating each row.

    Each plate runs inside its own savepoint so one row's failure (a permission
    gap, a missing plate, a guard throw) rolls back only that row and is reported
    back, instead of aborting the whole batch. Reuses the existing per-vehicle
    controllers verbatim — no parallel mutation logic.
    """
    results = []
    for plate in _coerce_plates(plates):
        sp = "sp" + frappe.generate_hash(length=10)
        frappe.db.savepoint(sp)
        try:
            res = action(plate)
            frappe.db.release_savepoint(sp)
            results.append({"plate": plate, "ok": True, **(res or {})})
        except Exception as e:
            frappe.db.rollback(save_point=sp)
            results.append({"plate": plate, "ok": False, "error": str(e)})
    succeeded = sum(1 for r in results if r["ok"])
    return {
        "ok": succeeded == len(results),
        "succeeded": succeeded,
        "failed": len(results) - succeeded,
        "results": results,
    }


@frappe.whitelist(methods=["POST"])
def bulk_stop_vehicles(plates, reason=None):
    """Stop several vehicles at once, reusing stop_vehicle per plate."""
    frappe.has_permission("Salis Vehicle", "write", throw=True)
    return _bulk_apply(plates, lambda p: stop_vehicle(p, reason=reason))


@frappe.whitelist(methods=["POST"])
def bulk_workshop_in(plates, expected_return=None, notes=None):
    """Send several vehicles to the workshop at once, reusing workshop_in per plate."""
    frappe.has_permission("Salis Vehicle", "write", throw=True)
    return _bulk_apply(plates, lambda p: workshop_in(p, expected_return=expected_return, notes=notes))


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
    lock_vehicle(vehicle)

    incident = frappe.db.get_value(
        "Vehicle Incident",
        {"vehicle": vehicle, "incident_type": "Theft", "docstatus": 1,
         "status": ["in", ("Open", "Under Review")]},
        ["name", "previous_driver", "previous_status"],
        as_dict=True,
        order_by="creation desc",
    )
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
    frappe.db.set_value("Vehicle Incident", incident.name, "status", "Closed")
    add_timeline_note(
        "Salis Vehicle", vehicle, _("Recovered; theft report {0} closed.").format(incident.name)
    )
    _publish_fleet_update(plate, "recover")
    return {"ok": True, "incident": incident.name}
