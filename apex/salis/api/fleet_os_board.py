# Copyright (c) 2026, afmcoltd
"""The /fleet-os board payload — the fleet read, and the shape the page renders.

``fleet_os.get_fleet_os`` is one whitelisted call over one screen of data, and
everything that decides what that screen contains lives here: which fields are
read off a vehicle, how a driver appears on a card, how an incident becomes a
stolen flag, and how a write-off becomes a damage row.

The split inside this module is deliberate and is the point of it. The ``_read_*``
functions touch the database and nothing else — each is one bounded query, and
each is run through :func:`_read` so a single failing enrichment degrades to a
notice instead of blanking the board. The shapers below them
(:func:`_vehicle_status`, :func:`_sheet_for`, :func:`_driver_card`,
:func:`_history_by_vehicle`, :func:`_incident_buckets`, :func:`_damage_rows`)
take plain rows and return plain rows, so the render contract the SPA depends on
can be exercised without a bench, a site or a database.

Contract: the ``vehicles`` list item shape matches exactly what the page's render
code reads (``v.plate``, ``v.history``, ``v.current_driver``, ``h.date_receive``
…), so the design's render functions run unchanged. Project scope and the
permlevel-1 PII gate are applied here, on the read — never left to the client.
"""

from __future__ import annotations

import re

import frappe
from frappe import _
from frappe.utils import date_diff, getdate, today

from apex.salis.api.fleet_reader import scope_filter, scoped_vehicles

_VEHICLE_FIELDS = [
    "name", "plate_number", "vehicle_category", "status",
    "rental_office", "project", "current_driver",
    "planned_fuel_grade", "planned_daily_fuel",
    "compliance_status", "next_expiry_date",
]

_STATUS_MAP = {
    "Stopped": "stopped",
    "Under Maintenance": "workshop",
    "Released": "stopped",
}


def driver_pii_visible() -> bool:
    """Whether this role may see a driver's identifying columns.

    The gate is permlevel 1 on Salis Driver: a role without read access there
    gets the driver's display name and nothing that identifies the person —
    ``driver_id`` and ``phone`` are blanked, not omitted, so the payload shape
    never changes with the reader. Every fleet-OS surface that carries a driver
    asks HERE, so the board, the typeahead and the audit timeline can never
    disagree about who is allowed to see what."""
    return 1 in frappe.get_meta("Salis Driver").get_permlevel_access("read")


def _vehicle_status(status: str, has_driver: bool, theft=None) -> str:
    """Map a Salis Vehicle.status to the design's vehicle_status string.

    Theft is not one of Salis Vehicle.status's four options — reporting one submits a
    Theft Vehicle Incident and the controller flips the vehicle to "Stopped" — so the
    board's stolen state has to come from the open incident, or it reads as an ordinary
    stop and the board's stolen filter can never match a vehicle."""
    if theft and theft.get("status") != "closed":
        return "stolen"
    if status == "Active":
        return "assigned" if has_driver else "available"
    return _STATUS_MAP.get(status, "available")


_MOTORCYCLE_TOKENS = ("MOTOR", "BIKE", "SCOOTER", "\u062f\u0628\u0627\u0628", "\u062f\u0631\u0627\u062c")

_MOTORCYCLE_PATTERN = re.compile(
    r"|".join(r"\b" + re.escape(token) + r"\w*" for token in _MOTORCYCLE_TOKENS),
    re.IGNORECASE,
)


def _sheet_for(category: str | None) -> str:
    """Best-effort CAR / MOTORCYCLE bucket for the design's type filter,
    derived from the category name (the design only has these two chips).

    The tokens are matched at a WORD BOUNDARY, not as bare substrings. Vehicle
    Category.category_name is a free Data field an admin types, so a bare substring test
    lets an unrelated category carrying one of these letters inside a longer word land in
    the wrong bucket \u2014 the same shape as the a/c-matched-jacket defect this repo already
    fixed in resident_request.py. The trailing \\w* keeps the plural and the compound
    ('MOTORBIKES', '\u062f\u0631\u0627\u062c\u0627\u062a') matching, which a bare \\b...\\b would have dropped."""
    if not category:
        return "CAR"
    return "MOTORCYCLE" if _MOTORCYCLE_PATTERN.search(category) else "CAR"


def _driver_card(driver, driver_row, show_pii, date_receive="", date_deliver="",
                 status="Active", project="") -> dict:
    """One driver as the design renders them, in the design's exact key set.

    The board shows a driver in two places — every row of a vehicle's assignment
    history, and the current-driver panel — and the page reads the SAME thirteen
    keys in both. Building them here is what stops the two drifting apart when a
    key is added. ``driver_id`` falls back to the Salis Driver name when the row
    carries no external id, and both identifying columns collapse to "" without
    the permlevel-1 gate. The empty strings are placeholders the imported design
    reads but Salis does not yet source. Pure."""
    return {
        "driver_id": ((driver_row.get("driver_id") or driver or "") if show_pii else ""),
        "name_en": (driver_row.get("full_name") or ""),
        "name_ar": "",
        "mobile": ((driver_row.get("phone") or "") if show_pii else ""),
        "date_receive": date_receive,
        "date_deliver": date_deliver,
        "status": status,
        "project": project,
        "area": "",
        "reason": "",
        "notes": "",
        "branch_receive": "",
        "branch_deliver": "",
    }


def _history_by_vehicle(assignments, drivers, show_pii) -> dict[str, list]:
    """Group assignment rows into each vehicle's driver history, oldest first.

    An assignment counts as live only when it is Active, submitted AND has no end
    date — a submitted row someone ended keeps its Active status, so the end date
    is what decides. Pure: assignments and the driver index are the whole input."""
    history: dict[str, list] = {}
    for a in assignments:
        driver_row = drivers.get(a.driver) or {}
        is_active = a.status == "Active" and a.docstatus == 1 and not a.end_date
        history.setdefault(a.vehicle, []).append(
            _driver_card(
                a.driver,
                driver_row,
                show_pii,
                date_receive=str(a.start_date or ""),
                date_deliver=str(a.end_date or ""),
                status="Active" if is_active else "Stopped",
                project=(a.project or ""),
            )
        )
    return history


def _current_driver_card(vehicle, history, drivers, show_pii):
    """The panel's current-driver card, or None when the vehicle has no driver.

    Prefers the vehicle's own live assignment row so the card carries the real
    receive date; falls back to a bare card built from the vehicle's
    ``current_driver`` link when the link outlives its assignment. Pure."""
    if not vehicle.get("current_driver"):
        return None
    active = next(
        (h for h in history if h.get("status") == "Active" and not h.get("date_deliver")), None
    )
    if active:
        return dict(active)
    return _driver_card(
        vehicle.current_driver,
        drivers.get(vehicle.current_driver) or {},
        show_pii,
        status="Active",
        project=(vehicle.project or ""),
    )


def _incident_buckets(incidents) -> tuple[dict, dict]:
    """Split submitted incidents into per-vehicle accidents and one theft each.

    A vehicle keeps at most one theft — the open one wins over a closed one, so a
    vehicle stolen twice reads as stolen while the second report is open. Every
    other incident type accumulates in ``accidents``, newest first (the caller
    reads them in query order). Pure."""
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
            cur = theft.get(inc.vehicle)
            if cur is None or (cur.get("status") == "closed" and row["status"] != "closed"):
                theft[inc.vehicle] = row
        else:
            accidents.setdefault(inc.vehicle, []).append(row)
    return accidents, theft


def _damage_rows(write_offs) -> dict[str, list]:
    """Group submitted write-offs into each vehicle's damage cases. An approved or
    closed case reads as ``completed``; anything else keeps its own lowercased
    status. Pure."""
    damages: dict[str, list] = {}
    for w in write_offs:
        damages.setdefault(w.vehicle, []).append({
            "case": w.name,
            "date": str(getdate(w.creation) if w.creation else ""),
            "status": "completed" if w.status in ("Approved", "Closed") else (w.status or "").lower(),
            "cost": w.estimated_cost or 0,
            "estimated_cost": w.estimated_cost or 0,
            "recommended_action": w.recommended_action or "",
            "description": w.damage_description or "",
            "has_evidence": bool(w.evidence),
        })
    return damages


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


def _read_category_fuel(cat_names) -> dict[str, str]:
    """The default fuel grade per Vehicle Category, upper-cased for the chips."""
    out: dict[str, str] = {}
    if cat_names:
        for c in frappe.get_all(
            "Vehicle Category",
            filters={"name": ["in", cat_names]},
            fields=["name", "default_fuel_type"],
        ):
            out[c.name] = (c.default_fuel_type or "").upper()
    return out


def _read_office_city(office_names) -> dict[str, str]:
    """The city per Rental Office — the board's "area" column."""
    out: dict[str, str] = {}
    if office_names:
        for o in frappe.get_all(
            "Rental Office",
            filters={"name": ["in", office_names]},
            fields=["name", "city"],
        ):
            out[o.name] = (o.city or "").strip().upper()
    return out


def _read_assignments(plates) -> list:
    """Every Vehicle Assignment touching the permitted fleet, oldest first."""
    return frappe.get_all(
        "Vehicle Assignment",
        filters={"vehicle": ["in", plates]},
        fields=["vehicle", "driver", "project", "start_date", "end_date", "status", "docstatus"],
        order_by="start_date asc",
        limit_page_length=0,
    )


def _read_drivers(driver_names) -> dict[str, dict]:
    """The Salis Driver rows behind every current driver and every assignment."""
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


def _read_incidents(plates) -> tuple[dict, dict]:
    """Submitted incidents for the permitted fleet, bucketed by
    :func:`_incident_buckets` into accidents and one theft per vehicle."""
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
    return _incident_buckets(incidents)


def _read_write_offs(plates) -> dict[str, list]:
    """Submitted damage write-offs for the permitted fleet, newest first."""
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
    return _damage_rows(write_offs)


def _read_workshop(plates) -> tuple[dict, set]:
    """The open Maintenance stop per vehicle plus the set already overstaying.

    Open means submitted with no return date — the invariant the overstay rule
    and the workshop release both rely on. The earliest open stop wins when a
    vehicle somehow carries two."""
    from apex.salis.tasks import _overstay_stops

    stops = frappe.get_all(
        "Vehicle Suspension",
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
    by_vehicle: dict[str, dict] = {}
    for s in stops:
        by_vehicle.setdefault(s.vehicle, s)
    overstay = {r.vehicle for r in _overstay_stops()}
    return by_vehicle, overstay


def build_board() -> dict:
    """The whole board: the permitted fleet in the design's exact vehicle shape.

    Project scope is enforced server-side: a scoped user with no permitted
    project gets an empty list. N+1-free — one bounded query per enrichment,
    grouped in Python.

    An empty result carries a typed ``reason`` so the page can tell the two apart:
    ``scope_empty`` (the user is scoped to no project — an access gap) vs
    ``data_empty`` (the permitted fleet is genuinely empty). A non-empty result
    has ``reason: None``. Filtered-empty stays a client concern (the page knows
    its own active filters).
    """
    show_pii = driver_pii_visible()
    reader_errors: list = []
    _unscoped, _projects, base_filters = scope_filter()
    if base_filters is None:
        return {"vehicles": [], "reason": "scope_empty", "reader_errors": []}

    vehicles = scoped_vehicles(fields=_VEHICLE_FIELDS, base_filters=base_filters)
    if not vehicles:
        return {"vehicles": [], "reason": "data_empty", "reader_errors": []}

    cat_names = list({v.vehicle_category for v in vehicles if v.get("vehicle_category")})
    cat_fuel = _read(
        reader_errors, _("fuel grades"), lambda: _read_category_fuel(cat_names), {}
    )

    office_names = list({v.rental_office for v in vehicles if v.get("rental_office")})
    office_city = _read(
        reader_errors, _("Rental Office"), lambda: _read_office_city(office_names), {}
    )

    driver_names = {v.current_driver for v in vehicles if v.get("current_driver")}

    plates = [v.name for v in vehicles]
    assignments = _read(
        reader_errors, _("assignments"), lambda: _read_assignments(plates), []
    )
    for a in assignments:
        if a.get("driver"):
            driver_names.add(a.driver)

    drivers = _read(reader_errors, _("drivers"), lambda: _read_drivers(driver_names), {})

    history_by_vehicle = _history_by_vehicle(assignments, drivers, show_pii)

    accidents_by_vehicle, theft_by_vehicle = _read(
        reader_errors, _("incidents"), lambda: _read_incidents(plates), ({}, {})
    )

    damages_by_vehicle = _read(
        reader_errors, _("damages"), lambda: _read_write_offs(plates), {}
    )

    workshop_by_vehicle, workshop_overstay = _read(
        reader_errors, _("workshop status"), lambda: _read_workshop(plates), ({}, set())
    )

    out = []
    for v in vehicles:
        history = history_by_vehicle.get(v.name, [])
        ws = workshop_by_vehicle.get(v.name)
        ws_date = str(ws.stop_date) if ws and ws.stop_date else ""
        out.append({
            "plate": v.plate_number or v.name,
            "vehicle_type": v.vehicle_category or "",
            "fuel": cat_fuel.get(v.vehicle_category, ""),
            "planned_fuel_grade": v.planned_fuel_grade or "",
            "planned_daily_fuel": v.planned_daily_fuel or 0,
            "compliance_status": v.compliance_status or "",
            "next_expiry_date": str(v.next_expiry_date or ""),
            "rental_office": v.rental_office or "",
            "sheet": _sheet_for(v.vehicle_category),
            "area": office_city.get(v.rental_office or "", ""),
            "project": v.project or "",
            "vehicle_status": _vehicle_status(
                v.status, bool(v.get("current_driver")), theft_by_vehicle.get(v.name)
            ),
            "workshop_notes": (ws.notes or "") if ws else "",
            "workshop_date": ws_date,
            "days_in_workshop": (date_diff(today(), ws.stop_date) if ws and ws.stop_date else 0),
            "workshop_overstay": v.name in workshop_overstay,
            "current_driver": _current_driver_card(v, history, drivers, show_pii),
            "history": history,
            "damages": damages_by_vehicle.get(v.name, []),
            "accidents": accidents_by_vehicle.get(v.name, []),
            "stolen_info": theft_by_vehicle.get(v.name),
            "notes": "",
        })

    return {"vehicles": out, "reason": None, "reader_errors": reader_errors}
