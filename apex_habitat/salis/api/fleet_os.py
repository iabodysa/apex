"""Fleet OS supervisor dashboard API (read + live operations).

Backs the ``/fleet`` www page, which is the fleet supervisor's single-screen
dashboard. The page is a faithful copy of the supervisor's own design; this
module replaces the design's embedded JSON with LIVE Salis data and routes its
operations to the real DocTypes.

Contract: :func:`get_fleet_os` returns a ``vehicles`` list whose item / history
shape matches exactly what the page's render code reads (``v.plate``,
``v.history``, ``v.current_driver``, ``h.date_receive`` …), so the design's
render functions run unchanged. The reader is N+1-free: bounded ``get_all``
queries (vehicles, the drivers they reference, all assignments, all incidents,
all damage write-offs) plus the Vehicle Category lookup, then grouped in Python.

Every endpoint is permission-gated on ``Salis Vehicle`` and project-scoped
server-side through the SAME ``_permitted_projects`` resolver the dispatch
board, fleet control board and the list-view ``permission_query_conditions``
use, so the dashboard never shows (or mutates) a project a scoped supervisor
could not already see. Writes reuse the existing controllers (Vehicle
Assignment, Vehicle Stop, Vehicle Incident) — no parallel logic.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import date_diff, getdate, today

from apex_habitat.salis.api.dispatch_board import _permitted_projects
from apex_habitat.salis.api.fleet_reader import scope_filter, scoped_vehicles
from apex_habitat.salis.utils import (
    add_timeline_note,
    close_open_stop,
    lock_vehicle,
    reassign_vehicle_driver,
)


def _publish_fleet_update(plate: str | None = None, action: str | None = None) -> None:
    """Signal the /fleet board to refetch ahead of its poll. Routed to the Salis
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


# [#mqc6q1]
_STATUS_MAP = {
    "Stopped": "stopped",
    "Under Maintenance": "workshop",
    "Released": "stopped",
}

# [#90ru7b]
_STOP_REASON_MAP = {
    "maintenance": "Maintenance",
    "rental return": "Rental Return",
    "rental": "Rental Return",
    "return": "Rental Return",
}


def _vehicle_status(status: str, has_driver: bool) -> str:
    """Map a Salis Vehicle.status to the design's vehicle_status string."""
    if status == "Active":
        return "assigned" if has_driver else "available"
    return _STATUS_MAP.get(status, "available")


def _sheet_for(category: str | None) -> str:
    """Best-effort CAR / MOTORCYCLE bucket for the design's type filter,
    derived from the category name (the design only has these two chips)."""
    if not category:
        return "CAR"
    upper = category.upper()
    # [#8m3t6n]
    if any(tok in upper for tok in ("MOTOR", "BIKE", "SCOOTER", "\u062f\u0628\u0627\u0628", "\u062f\u0631\u0627\u062c")):
        return "MOTORCYCLE"
    return "CAR"


def _read(reader_errors: list, reader: str, fn, default):
    """Run one secondary reader, isolating its failure from the board.

    The vehicle set is fatal (no board without it); every enrichment reader
    (drivers, assignments, incidents, write-offs, category fuel) is best-effort —
    a failure in one returns ``default`` and is recorded in ``reader_errors`` so
    the page can show a dismissible inline notice instead of a blank screen.
    """
    try:
        return fn()
    except Exception:
        frappe.log_error(
            message=frappe.get_traceback(),
            title=f"Fleet OS reader failed: {reader}"[:140],
        )
        reader_errors.append({"reader": reader, "error": _("Could not load {0}.").format(_(reader))})
        return default


def _resolve_plate(plate: str, ptype: str = "write") -> str:
    """Resolve a plate string from the dashboard to a Salis Vehicle name,
    permission-checked. Matches plate_number, then plate_normalized, then name.
    Raises if not found or not permitted. ``ptype`` is "write" for the action
    endpoints (the default) and "read" for read-only ones (the timeline)."""
    if not plate:
        frappe.throw(_("Plate is required."))
    name = frappe.db.get_value("Salis Vehicle", {"plate_number": plate}, "name")
    if not name:
        normalized = "".join(str(plate).split()).upper()
        name = frappe.db.get_value("Salis Vehicle", {"plate_normalized": normalized}, "name")
    if not name and frappe.db.exists("Salis Vehicle", plate):
        name = plate
    if not name:
        frappe.throw(_("Vehicle {0} not found.").format(plate))
    frappe.has_permission("Salis Vehicle", ptype, doc=name, throw=True)
    return name


# [#tnn6ln]
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
    # [#8178ig]
    show_pii = 1 in frappe.get_meta("Salis Driver").get_permlevel_access("read")
    reader_errors: list = []
    _unscoped, _projects, base_filters = scope_filter()
    # base_filters is None only for a scoped user with no permitted project.
    if base_filters is None:
        return {"vehicles": [], "reason": "scope_empty", "reader_errors": []}

    vehicles = scoped_vehicles(
        fields=[
            "name", "plate_number", "vehicle_category", "status",
            "rental_office", "project", "current_driver",
            "planned_fuel_grade", "planned_daily_fuel_sar",
            "compliance_status", "next_expiry_date",
        ],
        base_filters=base_filters,
    )
    if not vehicles:
        return {"vehicles": [], "reason": "data_empty", "reader_errors": []}

    # [#f8i05f]
    cat_names = list({v.vehicle_category for v in vehicles if v.get("vehicle_category")})

    def _read_cat_fuel():
        out: dict[str, str] = {}
        if cat_names:
            for c in frappe.get_all(
                "Vehicle Category",
                filters={"name": ["in", cat_names]},
                fields=["name", "default_fuel_type"],
            ):
                out[c.name] = (c.default_fuel_type or "").upper()
        return out

    cat_fuel: dict[str, str] = _read(reader_errors, _("fuel grades"), _read_cat_fuel, {})

    # [#ev30tz]
    driver_names = {v.current_driver for v in vehicles if v.get("current_driver")}

    # [#nfkzsx]
    plates = [v.name for v in vehicles]
    assignments = _read(
        reader_errors, _("assignments"),
        lambda: frappe.get_all(
            "Vehicle Assignment",
            filters={"vehicle": ["in", plates]},
            fields=["vehicle", "driver", "project", "start_date", "end_date", "status", "docstatus"],
            order_by="start_date asc",
            limit_page_length=0,
        ),
        [],
    )
    for a in assignments:
        if a.get("driver"):
            driver_names.add(a.driver)

    def _read_drivers():
        out: dict[str, dict] = {}
        if driver_names:
            for d in frappe.get_all(
                "Salis Driver",
                filters={"name": ["in", list(driver_names)]},
                fields=["name", "full_name", "driver_id", "phone"],
                limit_page_length=0,
            ):
                out[d.name] = d
        return out

    drivers: dict[str, dict] = _read(reader_errors, _("drivers"), _read_drivers, {})

    history_by_vehicle: dict[str, list] = {}
    for a in assignments:
        d = drivers.get(a.driver) or {}
        # [#cpmrad]
        is_active = a.status == "Active" and a.docstatus == 1 and not a.end_date
        history_by_vehicle.setdefault(a.vehicle, []).append({
            "driver_id": ((d.get("driver_id") or a.driver or "") if show_pii else ""),
            "name_en": (d.get("full_name") or ""),
            "name_ar": "",
            "mobile": ((d.get("phone") or "") if show_pii else ""),
            "date_receive": str(a.start_date or ""),
            "date_deliver": str(a.end_date or ""),
            "status": "Active" if is_active else "Stopped",
            "project": (a.project or ""),
            "area": "",
            "reason": "",
            "notes": "",
            "branch_receive": "",
            "branch_deliver": "",
        })

    # Open/recent incidents + write-offs per vehicle, grouped in Python (N+1-free).
    # Scope is inherited: `plates` is already the project-permitted vehicle set.
    def _read_incidents():
        incidents = frappe.get_all(
            "Vehicle Incident",
            filters={"vehicle": ["in", plates], "docstatus": 1},
            fields=[
                "vehicle", "incident_type", "incident_date", "location",
                "report_number", "status", "estimated_cost", "description", "evidence",
            ],
            order_by="incident_date desc",
            limit_page_length=0,
        )
        accidents: dict[str, list] = {}
        theft: dict[str, dict] = {}
        for inc in incidents:
            row = {
                "type": inc.incident_type or "",
                "date": str(inc.incident_date or ""),
                "location": inc.location or "",
                "report_number": inc.report_number or "",
                "status": "closed" if inc.status == "Closed" else (inc.status or "").lower(),
                "cost": inc.estimated_cost or 0,
                "estimated_cost": inc.estimated_cost or 0,
                "description": inc.description or "",
                "has_evidence": bool(inc.evidence),
            }
            if inc.incident_type == "Theft":
                # First (most recent, non-closed preferred) theft drives the card stripe.
                cur = theft.get(inc.vehicle)
                if cur is None or (cur.get("status") == "closed" and row["status"] != "closed"):
                    theft[inc.vehicle] = row
            else:
                accidents.setdefault(inc.vehicle, []).append(row)
        return accidents, theft

    accidents_by_vehicle, theft_by_vehicle = _read(
        reader_errors, _("incidents"), _read_incidents, ({}, {})
    )

    def _read_write_offs():
        write_offs = frappe.get_all(
            "Vehicle Damage Write-Off",
            filters={"vehicle": ["in", plates], "docstatus": 1},
            fields=[
                "name", "vehicle", "creation", "status", "estimated_cost",
                "damage_description", "recommended_action", "evidence",
            ],
            order_by="creation desc",
            limit_page_length=0,
        )
        damages: dict[str, list] = {}
        for w in write_offs:
            damages.setdefault(w.vehicle, []).append({
                "case": w.name,
                "date": str(getdate(w.creation) if w.creation else ""),
                # Front-end shows a "repaired" chip on 'completed'; Approved/Closed map to it.
                "status": "completed" if w.status in ("Approved", "Closed") else (w.status or "").lower(),
                "cost": w.estimated_cost or 0,
                "estimated_cost": w.estimated_cost or 0,
                "recommended_action": w.recommended_action or "",
                "description": w.damage_description or "",
                "has_evidence": bool(w.evidence),
            })
        return damages

    damages_by_vehicle: dict[str, list] = _read(reader_errors, _("damages"), _read_write_offs, {})

    # Workshop lane: per-vehicle open Maintenance stop -> entry date, days-in-workshop,
    # overstay flag and notes. Reuses tasks._overstay_stops (the single overstay rule)
    # so the board can never disagree with the alert/number card.
    def _read_workshop():
        from apex_habitat.salis.tasks import _overstay_stops

        stops = frappe.get_all(
            "Vehicle Stop",
            filters={
                "vehicle": ["in", plates],
                "stop_reason": "Maintenance",
                "docstatus": 1,
                "return_date": ["is", "not set"],
            },
            fields=["vehicle", "stop_date", "notes"],
            order_by="stop_date asc",
            limit_page_length=0,
        )
        # Earliest open stop per vehicle drives the lane (ordered asc above).
        by_vehicle: dict[str, dict] = {}
        for s in stops:
            by_vehicle.setdefault(s.vehicle, s)
        overstay = {r.vehicle for r in _overstay_stops()}
        return by_vehicle, overstay

    workshop_by_vehicle, workshop_overstay = _read(
        reader_errors, _("workshop status"), _read_workshop, ({}, set())
    )

    out = []
    for v in vehicles:
        cd = None
        if v.get("current_driver"):
            # [#8sgfo9]
            hist = history_by_vehicle.get(v.name, [])
            active = next((h for h in hist if h.get("status") == "Active" and not h.get("date_deliver")), None)
            if active:
                cd = dict(active)
            else:
                d = drivers.get(v.current_driver) or {}
                cd = {
                    "driver_id": ((d.get("driver_id") or v.current_driver or "") if show_pii else ""),
                    "name_en": (d.get("full_name") or ""), "name_ar": "",
                    "mobile": ((d.get("phone") or "") if show_pii else ""), "date_receive": "", "date_deliver": "",
                    "status": "Active", "project": (v.project or ""), "area": "",
                    "reason": "", "notes": "", "branch_receive": "", "branch_deliver": "",
                }
        ws = workshop_by_vehicle.get(v.name)
        ws_date = str(ws.stop_date) if ws and ws.stop_date else ""
        out.append({
            "plate": v.plate_number or v.name,
            "vehicle_type": v.vehicle_category or "",
            "fuel": cat_fuel.get(v.vehicle_category, ""),
            # Real planned-fuel plan off Salis Vehicle (was always the design's "—").
            "planned_fuel_grade": v.planned_fuel_grade or "",
            "planned_daily_fuel_sar": v.planned_daily_fuel_sar or 0,
            # Compliance status + next expiry drive the card's pre-stop expiry flag.
            "compliance_status": v.compliance_status or "",
            "next_expiry_date": str(v.next_expiry_date or ""),
            "rental_office": v.rental_office or "",
            "sheet": _sheet_for(v.vehicle_category),
            "area": "",  # [#6ptyey]
            "project": v.project or "",
            "vehicle_status": _vehicle_status(v.status, bool(v.get("current_driver"))),
            # Workshop lane: entry date, days-in-workshop and the overstay flag off the
            # open Maintenance stop (the inline return is the existing workshop_out action).
            "workshop_notes": (ws.notes or "") if ws else "",
            "workshop_date": ws_date,
            "days_in_workshop": (date_diff(today(), ws.stop_date) if ws and ws.stop_date else 0),
            "workshop_overstay": v.name in workshop_overstay,
            "current_driver": cd,
            "history": history_by_vehicle.get(v.name, []),
            # [#a3imrv]
            "damages": damages_by_vehicle.get(v.name, []),
            "accidents": accidents_by_vehicle.get(v.name, []),
            "stolen_info": theft_by_vehicle.get(v.name),
            "notes": "",
        })

    return {"vehicles": out, "reason": None, "reader_errors": reader_errors}


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
    show_pii = 1 in frappe.get_meta("Salis Driver").get_permlevel_access("read")
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
        # driver_id is permlevel-1; only let a PII-bearing role match on it.
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
        # Scope to drivers free or on a permitted-project vehicle. The driver's own
        # project is advisory; the vehicle link is the operative scope (mirrors how
        # get_fleet_os scopes by Salis Vehicle.project).
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
    """Merged per-vehicle audit timeline for the /fleet panel Log tab.

    One descending feed of the vehicle's assignments, stops, incidents and
    Operations Alerts. Read-permission- and project-scope-gated through the SAME
    ``_resolve_plate`` resolver the actions use (in read mode), and the
    permlevel-1 PII gate blanks the driver id on assignment rows for a role
    without it. N+1-free: one bounded ``get_all`` per source, merged in Python.
    """
    vehicle = _resolve_plate(plate, ptype="read")
    show_pii = 1 in frappe.get_meta("Salis Driver").get_permlevel_access("read")

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
        "Vehicle Stop",
        filters={"vehicle": vehicle, "docstatus": ["<", 2]},
        fields=["name", "stop_reason", "stop_date", "return_date", "notes"],
        order_by="stop_date desc",
        limit_page_length=0,
    ):
        events.append({
            "kind": "stop",
            "date": str(s.stop_date or ""),
            "title": _(s.stop_reason) if s.stop_reason else _("Stop"),
            "ref_doctype": "Vehicle Stop",
            "ref_name": s.name,
            "return_date": str(s.return_date or ""),
            "notes": s.notes or "",
        })

    for inc in frappe.get_all(
        "Vehicle Incident",
        filters={"vehicle": vehicle, "docstatus": ["<", 2]},
        fields=["name", "incident_type", "incident_date", "status", "location"],
        order_by="incident_date desc",
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

    for al in frappe.get_all(
        "Operations Alert",
        filters={"vehicle": vehicle},
        fields=["name", "alert_type", "severity", "status", "raised_on", "message"],
        order_by="raised_on desc",
        limit_page_length=0,
    ):
        events.append({
            "kind": "alert",
            "date": str(al.raised_on or ""),
            "title": _(al.alert_type) if al.alert_type else _("Alert"),
            "ref_doctype": "Operations Alert",
            "ref_name": al.name,
            "severity": al.severity or "",
            "status": al.status or "",
            "message": al.message or "",
        })

    # Newest first; empty dates sort last (so undated rows never head the feed).
    events.sort(key=lambda e: e.get("date") or "", reverse=True)
    return {"events": events}


# [#76c7tt]
@frappe.whitelist(methods=["POST"])
def reassign(plate, driver_id, date=None):
    """Assign a driver to a vehicle by creating a submitted Vehicle Assignment.

    ``driver_id`` is the EXTERNAL fleet identifier (Salis Driver.driver_id), as
    the dashboard carries it; we resolve it to the Salis Driver name. The
    Vehicle Assignment controller handles the link side; we also set the
    vehicle's current_driver and the driver's current_vehicle so the live state
    matches immediately (the assignment alone does not mutate those).
    """
    vehicle = _resolve_plate(plate)
    if not driver_id:
        frappe.throw(_("Driver is required."))

    driver = frappe.db.get_value("Salis Driver", {"driver_id": driver_id}, "name")
    if not driver and frappe.db.exists("Salis Driver", driver_id):
        driver = driver_id
    if not driver:
        frappe.throw(_("Driver {0} not found.").format(driver_id))
    # [#cs6rw5]
    frappe.has_permission("Salis Driver", "write", doc=driver, throw=True)

    # Shared native reassign (end Active assignment[s] + submit a new one). The new
    # assignment's on_submit stamps current_driver / current_vehicle, so no manual
    # link write is needed here. The board allows a refresh to the same driver.
    assignment = reassign_vehicle_driver(vehicle, driver, date)
    _publish_fleet_update(plate, "reassign")
    return {"ok": True, "assignment": assignment}


@frappe.whitelist(methods=["POST"])
def create_handover(plate, driver_id, date=None, odometer=None, checklist_template=None, condition_notes=None):
    """Create an OPTIONAL DRAFT Vehicle Handover for a just-reassigned vehicle.

    Called by /fleet AFTER reassign succeeds, only when the supervisor ticked the
    optional capture box. Reuses the native Vehicle Handover DocType/controller —
    no parallel handover logic. It is left as a DRAFT (insert only, never submit):
    the controller requires signed evidence before submit, so a manager later
    attaches it and submits via Desk (where the checklist UI + print format live).

    ``to_driver`` is the just-assigned driver; ``from_driver`` is the previous
    driver, read from the most recent Ended assignment reassign left behind. With
    no prior driver (a first-ever assignment) there is no custody to transfer, so
    no handover is drafted — the caller shows that as a benign notice.
    A checklist template, when given, is loaded via the existing template loader.
    """
    vehicle = _resolve_plate(plate)
    if not driver_id:
        frappe.throw(_("Driver is required."))

    to_driver = frappe.db.get_value("Salis Driver", {"driver_id": driver_id}, "name")
    if not to_driver and frappe.db.exists("Salis Driver", driver_id):
        to_driver = driver_id
    if not to_driver:
        frappe.throw(_("Driver {0} not found.").format(driver_id))
    frappe.has_permission("Vehicle Handover", "create", throw=True)

    # Previous driver = the driver on the latest Ended assignment for this vehicle
    # (reassign ends the prior Active row before opening the new one).
    prev = frappe.get_all(
        "Vehicle Assignment",
        filters={"vehicle": vehicle, "status": "Ended", "driver": ["!=", to_driver]},
        fields=["driver"],
        order_by="end_date desc, creation desc",
        limit_page_length=1,
    )
    from_driver = prev[0].driver if prev else None

    # No prior custodian: a handover from nobody is not a real transfer, and the
    # Handover.from_driver field fetch_if_empty-copies the vehicle's current_driver
    # (already the NEW driver here), which would self-equal to_driver and fail the
    # controller's "must differ" guard. Skip the draft instead of forcing one.
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

    if checklist_template and frappe.db.exists("Vehicle Handover Checklist Template", checklist_template):
        from apex_habitat.salis.doctype.vehicle_handover_checklist_template.vehicle_handover_checklist_template import (
            load_template_into_doc,
        )

        load_template_into_doc(doc.name, checklist_template)

    return {"ok": True, "handover": doc.name}


@frappe.whitelist(methods=["POST"])
def stop_vehicle(plate, reason=None):
    """Stop a vehicle and release its driver by submitting a Vehicle Stop.

    Vehicle Stop.on_submit flips Salis Vehicle.status to "Stopped". The free-text
    reason is mapped to the nearest no-evidence Select option (default "Other")
    so the submit never trips the evidence gate. The current assignment is ended
    and the driver link cleared to match the released state.
    """
    vehicle = _resolve_plate(plate)
    lock_vehicle(vehicle)
    stop_reason = _STOP_REASON_MAP.get((reason or "").strip().lower(), "Other")

    current_driver = frappe.db.get_value("Salis Vehicle", vehicle, "current_driver")

    doc = frappe.get_doc({
        "doctype": "Vehicle Stop",
        "vehicle": vehicle,
        "stop_reason": stop_reason,
        "stop_date": getdate(today()),
        "notes": (reason or ""),
    })
    doc.insert()
    doc.submit()  # [#mx3ts3]

    # [#q5vodj]
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
    doc.submit()  # [#taa8d4]
    _publish_fleet_update(plate, "theft")
    return {"ok": True, "incident": doc.name}


@frappe.whitelist(methods=["POST"])
def workshop_in(plate, expected_return=None, notes=None):
    """Send a vehicle to the workshop via a submittable Maintenance Vehicle Stop.

    Mirrors stop_vehicle/report_theft/reassign: the workshop event is now an
    audited submitted record, not a bare status flip. The Vehicle Stop controller
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
        "doctype": "Vehicle Stop",
        "vehicle": vehicle,
        "stop_reason": "Maintenance",
        "stop_date": getdate(today()),
        "notes": note,
    })
    doc.insert()
    doc.submit()  # on_submit captures previous_status + flips status to "Stopped".

    # Distinguish the workshop lane from a plain stop on the board; previous_status
    # was already captured by on_submit so the return path can still restore it.
    frappe.db.set_value("Salis Vehicle", vehicle, "status", "Under Maintenance")
    _publish_fleet_update(plate, "workshop_in")
    return {"ok": True, "stop": doc.name}


@frappe.whitelist(methods=["POST"])
def workshop_out(plate):
    """Return a vehicle from the workshop by closing its open Maintenance stop.

    Mirrors operations_control.release_vehicle: stamp the workshop-exit fields on
    the open submitted Maintenance Vehicle Stop and cancel it, so the cancel leaves
    its own audit note. on_cancel only auto-restores when the vehicle still reads
    "Stopped"; since workshop_in parks it at "Under Maintenance", we restore the
    stop's captured previous_status here. Throws when there is no open workshop stop.
    """
    vehicle = _resolve_plate(plate)
    lock_vehicle(vehicle)

    stop = frappe.db.get_value(
        "Vehicle Stop",
        {"vehicle": vehicle, "stop_reason": "Maintenance", "docstatus": 1,
         "return_date": ["is", "not set"]},
        ["name", "previous_status"],
        as_dict=True,
        order_by="creation desc",
    )
    if not stop:
        frappe.throw(_("This vehicle has no open workshop stop to return."))

    # Shared native stop-close (stamp audit fields + cancel); same helper
    # operations_control.release_vehicle uses.
    close_open_stop(stop.name)
    # on_cancel skips its restore while status != "Stopped"; bring it back explicitly.
    if frappe.db.get_value("Salis Vehicle", vehicle, "status") == "Under Maintenance":
        frappe.db.set_value("Salis Vehicle", vehicle, "status", stop.previous_status or "Active")
    _publish_fleet_update(plate, "workshop_out")
    return {"ok": True, "stop": stop.name}


def _coerce_plates(plates) -> list[str]:
    """Normalize the plates param (a JSON array over HTTP, or a real list) to a
    de-duplicated, order-preserving list of non-empty plate strings."""
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
        # savepoint name must be a valid SQL identifier (a hex hash can start
        # with a digit, which MariaDB rejects) — prefix with a letter.
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
    # Gate the batch up front; each plate is re-checked per-doc in _resolve_plate.
    frappe.has_permission("Salis Vehicle", "write", throw=True)
    return _bulk_apply(plates, lambda p: stop_vehicle(p, reason=reason))


@frappe.whitelist(methods=["POST"])
def bulk_workshop_in(plates, expected_return=None, notes=None):
    """Send several vehicles to the workshop at once, reusing workshop_in per plate."""
    # Gate the batch up front; each plate is re-checked per-doc in _resolve_plate.
    frappe.has_permission("Salis Vehicle", "write", throw=True)
    return _bulk_apply(plates, lambda p: workshop_in(p, expected_return=expected_return, notes=notes))


@frappe.whitelist(methods=["POST"])
def recover(plate):
    """Recover a stopped/stolen vehicle back to service.

    When the vehicle has an open Theft Vehicle Incident on record, close it in the
    same transaction and restore the state it captured at report time
    (``previous_driver`` / ``previous_vehicle_status``) — so a recovered vehicle is
    not left with a Theft incident Open forever. With no theft on record (a plain
    stop), recover simply returns the vehicle to Active.
    """
    vehicle = _resolve_plate(plate)
    lock_vehicle(vehicle)

    incident = frappe.db.get_value(
        "Vehicle Incident",
        {"vehicle": vehicle, "incident_type": "Theft", "docstatus": 1,
         "status": ["in", ("Open", "Under Review")]},
        ["name", "previous_driver", "previous_vehicle_status"],
        as_dict=True,
        order_by="creation desc",
    )
    if not incident:
        frappe.db.set_value("Salis Vehicle", vehicle, "status", "Active")
        _publish_fleet_update(plate, "recover")
        return {"ok": True}

    # Restore the pre-theft driver only if the vehicle is still free (mirror the
    # incident's own on_cancel), then bring it back to its captured status.
    if incident.previous_driver and not frappe.db.get_value(
        "Salis Vehicle", vehicle, "current_driver"
    ):
        frappe.db.set_value("Salis Vehicle", vehicle, "current_driver", incident.previous_driver)
        frappe.db.set_value("Salis Driver", incident.previous_driver, "current_vehicle", vehicle)

    frappe.db.set_value(
        "Salis Vehicle", vehicle, "status", incident.previous_vehicle_status or "Active"
    )
    frappe.db.set_value("Vehicle Incident", incident.name, "status", "Closed")
    add_timeline_note(
        "Salis Vehicle", vehicle, _("Recovered; theft report {0} closed.").format(incident.name)
    )
    _publish_fleet_update(plate, "recover")
    return {"ok": True, "incident": incident.name}
