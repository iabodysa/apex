# Copyright (c) 2026, afmcoltd
"""Fleet employee self-service API — backs the /fleet employee page (my vehicle,
my recent trips, fuel request).

Unlike the supervisor board (fleet_os) these endpoints are IDENTITY-SCOPED: every
one resolves ``frappe.session.user`` to the caller's own Salis Driver and returns
ONLY that person's vehicle / trips / fuel requests. The client never supplies a
driver or vehicle id, so opening /fleet as an ordinary employee can never leak
another user's data. A user who is not linked to a Salis Driver (a normal office
employee with no fleet vehicle) gets a friendly EMPTY result, never a 403 — the
page renders its empty state.

The user -> Employee (user_id) -> Salis Driver (employee) resolution is the shared
session-only helper, which never reads a portal bearer cookie. "My vehicle" is the
driver's ``current_vehicle`` or, failing that, the vehicle on an Active Vehicle
Assignment — the SAME binding rule fuel writes enforce, so a fuel request can only
ever be raised against the caller's own vehicle. Fuel requests reuse the native
Fuel Request DocType and its controller validation/workflow (created Pending,
docstatus 0, for supervisor approval) — no new DocType is invented.
"""

import frappe
from frappe import _

from apex.salis.utils import (
    add_timeline_note,
    bound_vehicle,
    get_driver_for_session_user,
    period_quota,
)

from apex.apex_core.utils.system_write import system_insert

_VEHICLE_STATUS_KEY = {
    "Active": "assigned",
    "Under Maintenance": "workshop",
    "Stopped": "stopped",
    "Released": "stopped",
}

_TRIP_STATUS_KEY = {
    "Planned": "planned",
    "Dispatched": "inProgress",
    "Completed": "completed",
}

_REGISTRATION_TYPE = "Registration (Istimara)"


def _registration_expiry(vehicle):
    """The vehicle's registration (Istimara) expiry, else its next rolled-up expiry.

    Prefers the explicit ``Registration (Istimara)`` compliance document (the true
    registration date the employee cares about) and falls back to the vehicle's
    ``next_expiry_date`` rollup. Returns an ISO date string or None."""
    reg = frappe.db.get_value(
        "Salis Vehicle Compliance",
        {"parent": vehicle, "parenttype": "Salis Vehicle", "compliance_type": _REGISTRATION_TYPE},
        "expiry_date",
        order_by="expiry_date desc",
    )
    reg = reg or frappe.db.get_value("Salis Vehicle", vehicle, "next_expiry_date")
    return frappe.utils.cstr(reg) if reg else None


@frappe.whitelist()
def get_my_vehicle():
    """The vehicle currently assigned to the session user (read).

    Identity-scoped: resolves the user to their Salis Driver, then returns the
    bound vehicle (current_vehicle, else Active Vehicle Assignment). Returns
    ``{"vehicle": None}`` — a clean empty state, never a 403 — when the user is
    not a driver or has no vehicle bound. Read-only, no commit.

    The payload is shaped for the employee page's "My vehicle" card: plate,
    model (category label), office (project label), a status key mapped to the
    page's status-pill vocabulary, odometer, and the registration expiry."""
    driver = get_driver_for_session_user(frappe.session.user)
    vehicle = bound_vehicle(driver) if driver else None
    if not vehicle:
        return {"vehicle": None}

    v = frappe.db.get_value(
        "Salis Vehicle", vehicle,
        ["name", "plate_number", "vehicle_category", "status", "odometer", "project"],
        as_dict=True,
    ) or {}

    project = v.get("project")
    office = (frappe.db.get_value("Project", project, "project_name") or project) if project else None

    return {
        "vehicle": {
            "name": v.get("name"),
            "plate": v.get("plate_number"),
            "model": v.get("vehicle_category") or None,
            "office": office,
            "status": _VEHICLE_STATUS_KEY.get(v.get("status"), "available"),
            "odometerKm": frappe.utils.cint(v.get("odometer")) or None,
            "registrationExpiry": _registration_expiry(vehicle),
        }
    }


@frappe.whitelist()
def get_my_recent_trips(days=30, limit=20):
    """The session user's recent Dispatch Trips, newest first (read).

    Identity-scoped via endpoint-scoped ``get_all`` filtered on the caller's own
    driver, so it can only ever return the caller's own trips — the client never
    supplies a driver id. Cancelled trips are omitted. Returns ``[]`` (empty
    state) when the user is not a driver. Read-only, no commit.

    Each row is shaped for the "My trips" card: route title, date/time, distance
    (from the odometer delta when both readings are present), and a status key
    mapped to the page's trip-pill vocabulary."""
    driver = get_driver_for_session_user(frappe.session.user)
    if not driver:
        return []

    since = frappe.utils.add_days(frappe.utils.today(), -(frappe.utils.cint(days) or 30))
    rows = frappe.get_all(
        "Dispatch Trip",
        filters={
            "driver": driver,
            "trip_date": [">=", since],
            "status": ["!=", "Cancelled"],
        },
        fields=[
            "name", "route_plan", "shift_name", "trip_date", "depart_time",
            "odometer_start", "odometer_end", "status",
        ],
        order_by="trip_date desc, depart_time desc",
        limit=frappe.utils.cint(limit) or 20,
    )

    route_names = {r["route_plan"] for r in rows if r.get("route_plan")}
    labels = {}
    if route_names:
        for rp in frappe.get_all(
            "Route Plan", filters={"name": ["in", list(route_names)]},
            fields=["name", "route_name"],
        ):
            labels[rp["name"]] = rp.get("route_name") or rp["name"]

    out = []
    for r in rows:
        start, end = r.get("odometer_start"), r.get("odometer_end")
        distance = None
        if start is not None and end is not None and end > start:
            distance = frappe.utils.cint(end) - frappe.utils.cint(start)
        title = labels.get(r.get("route_plan")) or r.get("shift_name") or _("Dispatch trip")
        out.append(
            {
                "id": r["name"],
                "title": title,
                "date": frappe.utils.cstr(r["trip_date"]) if r.get("trip_date") else None,
                "when": frappe.utils.cstr(r["depart_time"])[:5] if r.get("depart_time") else None,
                "distanceKm": distance,
                "status": _TRIP_STATUS_KEY.get(r.get("status"), "planned"),
            }
        )
    return out


@frappe.whitelist()
def get_fuel_stations():
    """The active Fuel Platforms to pick as the fuel-request station (read).

    Replaces the page's hard-coded station list. Returns a list of platform names
    (the Fuel Platform's autoname = its display name), active only. Read-only."""
    return frappe.get_all(
        "Fuel Platform",
        filters={"status": "Active"},
        pluck="name",
        order_by="platform_name asc",
    )


@frappe.whitelist(methods=["POST"])
def submit_fuel_request(litres, vehicle=None, fuel_grade=None, station=None, notes=None):
    """Raise a fuel request for the caller's OWN vehicle, pending approval (write).

    Identity-scoped: the driver is resolved from the session, never client-supplied.
    ``vehicle`` is optional and, when given, is honoured only after the binding check
    (it must be the caller's bound vehicle) — so an employee can never charge fuel to
    a vehicle that is not theirs by passing an arbitrary id; an unbound/omitted id
    falls back to their bound vehicle.

    Reuses the native Fuel Request DocType and its controller (Standard type,
    created Pending / docstatus 0 for the Fuel Request Workflow's supervisor
    approval) — no new DocType. ``litres`` -> requested_litres, ``station`` ->
    fuel_platform. ``fuel_grade`` and ``notes`` have no dedicated Fuel Request
    field, so they are preserved as a timeline note on the created request rather
    than dropped. Returns ``{"name": ...}``.

    The request carries the vehicle's Fuel Quota for its OWN request month, so the
    controller's allowance gate is live on this door too: with ``fuel_quota`` empty
    ``_guard_quota_allowance`` returns at its first line, and /fleet was drawing past
    an allocation the desk and the driver portal are both held to. An oversized draw
    is refused here, before insert, with the very message the desk raises. A vehicle
    with NO quota that month still submits — the allocation is what creates the
    ceiling, not this endpoint."""
    driver = get_driver_for_session_user(frappe.session.user)
    if not driver:
        frappe.throw(
            _("No fleet vehicle is assigned to you, so you cannot request fuel."),
            frappe.PermissionError,
        )

    bound = bound_vehicle(driver)
    if vehicle and vehicle != bound:
        frappe.throw(
            _("That vehicle is not assigned to you. You can only request fuel for your own vehicle."),
            frappe.PermissionError,
        )
    vehicle = bound
    if not vehicle:
        frappe.throw(
            _("No vehicle is assigned to you. Ask your supervisor to assign one before requesting fuel.")
        )

    litres = frappe.utils.flt(litres)
    if litres <= 0:
        frappe.throw(_("Enter how many litres you need."))

    request_date = frappe.utils.today()
    quota = period_quota(vehicle, request_date[:7], ["name"])
    doc = frappe.get_doc(
        {
            "doctype": "Fuel Request",
            "request_type": "Standard",
            "vehicle": vehicle,
            "driver": driver,
            "fuel_quota": quota.name if quota else None,
            "fuel_platform": station or None,
            "requested_litres": litres,
            "request_date": request_date,
            "status": "Pending",
        }
    )
    doc._guard_quota_allowance()
    system_insert(doc)

    extras = []
    if fuel_grade:
        extras.append(_("Requested grade: {0}").format(fuel_grade))
    if notes:
        extras.append(_("Note: {0}").format(notes))
    if extras:
        add_timeline_note("Fuel Request", doc.name, " · ".join(extras))

    return {"name": doc.name}


_FUEL_STATUS_KEY = {
    "Pending": "pending",
    "Approved": "approved",
    "Done": "completed",
    "Failed": "failed",
    "Reverted": "failed",
    "Cancelled": "cancelled",
}


@frappe.whitelist()
def get_my_fuel_requests(days=90, limit=30):
    """The session user's own fuel requests, newest first (read).

    Identity-scoped exactly as its siblings are: the driver comes from
    ``frappe.session.user``, never from a client-supplied id and never from a
    portal cookie, so an employee sees only what they raised. Returns ``[]`` for a
    user who is not a driver, so the page renders its empty state rather than a
    permission error. Read-only, no commit."""
    driver = get_driver_for_session_user(frappe.session.user)
    if not driver:
        return []

    since = frappe.utils.add_days(frappe.utils.today(), -(frappe.utils.cint(days) or 90))
    rows = frappe.get_all(
        "Fuel Request",
        filters={
            "driver": driver,
            "request_date": [">=", since],
            "docstatus": ["<", 2],
        },
        fields=[
            "name", "request_date", "request_type", "vehicle", "fuel_platform",
            "requested_litres", "amount", "status",
        ],
        order_by="request_date desc, creation desc",
        limit=frappe.utils.cint(limit) or 30,
    )

    plates = {}
    vehicles = {r["vehicle"] for r in rows if r.get("vehicle")}
    if vehicles:
        plates = {
            v["name"]: v["plate_number"]
            for v in frappe.get_all(
                "Salis Vehicle",
                filters={"name": ["in", list(vehicles)]},
                fields=["name", "plate_number"],
            )
        }

    return [
        {
            "name": r["name"],
            "date": r["request_date"],
            "type": r["request_type"],
            "vehicle": plates.get(r["vehicle"], r["vehicle"]),
            "station": r["fuel_platform"],
            "litres": r["requested_litres"],
            "amount": r["amount"],
            "status": r["status"],
            "statusKey": _FUEL_STATUS_KEY.get(r["status"], "pending"),
        }
        for r in rows
    ]
