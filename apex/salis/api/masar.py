# Copyright (c) 2026, afmcoltd
"""Masar (Worker Movement) portal endpoints.

Masar is the **Workers division of Salis** — the worker-transport experience on
the shared fleet backbone. This module is the endpoint surface and nothing else:
every whitelisted method the worker SPA and the driver portal call lives here,
under the dotted path the clients already hold, and each one resolves identity,
composes a payload and returns it.

The work those endpoints do is split by subject, and each half has exactly one
home:

  * :mod:`apex.salis.api.masar_routes` — trips, routes, stops and the ride ETA.
    Shared by the DRIVER route view and the WORKER transport view, which read the
    same trips from opposite ends.
  * :mod:`apex.salis.api.masar_worker` — the worker's identity boundary and the
    records that worker owns: housing, documents, custody, requests, contacts.

Both are re-exported here under their original names. Callers outside this module
(``driver_portal``, ``boarding_flow``, ``boarding_window``, ``route_supervisor``)
import them from ``masar``, and that stays true.

Driver-route endpoints resolve a presented driver credential first, then fall
back to a linked signed-in driver when no credential was presented. The client
never supplies a driver id. These route reads feed the worker view inside the
existing /driver portal and have no GL or write side effects.

The three documents a worker raises about himself — his Resident Request, his Transport Request,
his trip rating — are now written inside ``as_capacity(WORKER)`` under the Worker role's own
``create``. The endpoints stay ``allow_guest=True`` and ``frappe.session.user`` is Guest for the
request; the capacity is opened around the write only, after ``_resolve_worker`` has already
turned the QR token into an Employee. Authentication is the token, authorisation is the role.

The capacity is never a login: it exists for the duration of one write and is handed back in a
``finally``, so the role it carries is unreachable from outside. That is what makes granting it
read on those DocTypes safe — no request ever runs as it.

The Trip Start Log write (the worker's boarding self-confirm, appended to the trip's shared
execution log) now runs inside ``as_capacity(WORKER, employee)`` too. It is the driver's log, not
the worker's, so the Worker role's DocPerm alone cannot scope it; the record-level gate is
``apex.salis.permissions._trip_start_log_capacity_verdict``, which authorises a Worker capacity
write only when the resolved employee is on the trip's own manifest — the same forward resolution
``_worker_today_dispatch_trip`` already used to find that trip.
"""

import frappe
from frappe import _
from frappe.utils import cint

from apex.apex_core.utils.portal_identity import WORKER, as_capacity, portal_room
from apex.apex_core.utils.rate_limit_identity import rate_limit
from apex.apex_core.utils.role_assignment import role_holders_escalating
from apex.apex_core.utils.system_notify import notify_user_system
from apex.salis.api import boarding_window
from apex.salis.api.boarding import already_boarded
from apex.salis.api.driver_portal import _require_enabled, _resolve_driver
from apex.salis.utils import days_until as _days_until
from apex.salis.api.maps_links import _full_route_maps_url
from apex.salis.api.maps_links import _stop_waypoint
from apex.salis.api.masar_routes import (
    WORKER_SERVICE_LINES,
    _drop_finished_yesterday,
    _fmt_time,
    _is_upcoming_pickup,
    _ordered_stops,
    _ordered_trip_stops,
    _registered_trip_workers,
    _registered_workers,
    _route_destination_stop,
    _today_worker_trips,
    _worker_pickup_stop,
    _worker_today_dispatch_trip,
    _worker_transport_requests,
)
from apex.salis.api.masar_worker import (
    MASAR_TOKEN_COOKIE,
    _active_assignment,
    _attach_worker_photo,
    _building_in_charge,
    _clean_adhoc_passengers,
    _custody_issued_by,
    _fmt_date,
    _iqama_of,
    _net_custody_items,
    _request_status_timeline,
    _resolve_worker,
    _today_driver,
    _token_from_request,
    _worker_documents,
)

__all__ = [
    "MASAR_TOKEN_COOKIE",
    "WORKER_SERVICE_LINES",
    "_drop_finished_yesterday",
    "_registered_workers",
    "_stop_waypoint",
    "_token_from_request",
]

@frappe.whitelist()
def get_my_worker_route_today():
    """Read-only worker-transport trip view for the CURRENT driver.

    Resolves a presented driver credential first, then falls back to the linked
    signed-in driver when no credential was presented. Returns today's
    Workers-line route(s): for each trip, the route plan, its ordered stops (each
    with its Habitat housing pickup when linked), and the registered worker
    manifest carried by the linked Transport Request.

    Read-only. This feeds the future driver-portal worker view (Phase 1b); it
    posts no GL and writes nothing.

    Shape::

        {
          "driver": "DRV-000001",
          "date": "YYYY-MM-DD",
          "trips": [
            {
              "dispatch_trip": "DT-000007",
              "transport_request": "TR-000005",
              "route_plan": "RP-000005",
              "vehicle": "...", "depart_time": "06:30:00",
              "return_time": null, "status": "Planned",
              "expected_count": 3,
              "stops": [ { "stop_name": "...", "sequence": 1,
                           "accommodation_building": "...",
                           "pickup": { "building_name": "...", "city": "...",
                                       "google_maps_url": "..." } }, ... ],
              "workers": [ { "employee": "...", "employee_name": "...",
                             "pickup_point": "..." }, ... ]
            }
          ]
        }
    """
    _require_enabled()
    driver = _resolve_driver()
    trips = []
    for t in _today_worker_trips(driver):
        workers = _registered_trip_workers(t["name"], t.get("transport_request"))
        trips.append(
            {
                "dispatch_trip": t["name"],
                "trip_title": t.get("trip_title"),
                "route_assignment": t.get("route_assignment"),
                "route_template": t.get("route_template"),
                "project": t.get("project"),
                "transport_request": t.get("transport_request"),
                "transport_requests": t.get("transport_requests") or [],
                "route_plan": t.get("route_plan"),
                "vehicle": t.get("vehicle"),
                "depart_time": _fmt_time(t.get("depart_time")),
                "return_time": _fmt_time(t.get("return_time")),
                "status": t.get("status"),
                "expected_count": len(workers),
                "stops": _ordered_trip_stops(t["name"], t.get("route_plan")),
                "workers": workers,
            }
        )
    return {"driver": driver, "date": frappe.utils.today(), "trips": trips}

@frappe.whitelist()
def get_my_worker_route_summary() -> dict:
    """Read-only, identity-scoped *summary* of the current driver's worker route
    today — a compact roll-up for the standalone ``/masar`` page header.

    Resolves a presented driver credential first, then falls back to the linked
    signed-in driver when no credential was presented. Folds today's Workers-line
    trips into headline counts plus a single "next pickup" pointer (the earliest
    housing-pickup stop on the earliest trip). Read-only; writes nothing and posts
    no GL.

    Shape::

        {
          "driver": "DRV-000001",
          "date": "YYYY-MM-DD",
          "trip_count": 2,
          "stop_count": 5,
          "expected_total": 7,
          "next_pickup": {
            "dispatch_trip": "DT-000007", "depart_time": "06:30:00",
            "stop_name": "Housing Pickup", "sequence": 1,
            "building_name": "...", "city": "...", "google_maps_url": "..."
          }
        }
    """
    _require_enabled()
    driver = _resolve_driver()

    worker_trips = _today_worker_trips(driver)
    stop_count = 0
    expected_total = 0
    next_pickup = None
    for t in worker_trips:
        expected_total += len(
            _registered_trip_workers(t["name"], t.get("transport_request"))
        )
        stops = _ordered_trip_stops(t["name"], t.get("route_plan"))
        stop_count += len(stops)
        if next_pickup is None:
            for s in stops:
                if s.get("accommodation_building") and s.get("pickup"):
                    pickup = s["pickup"]
                    next_pickup = {
                        "dispatch_trip": t["name"],
                        "depart_time": _fmt_time(t.get("depart_time")),
                        "stop_name": s.get("stop_name"),
                        "sequence": s.get("sequence"),
                        "building_name": pickup.get("building_name"),
                        "city": pickup.get("city"),
                        "google_maps_url": pickup.get("google_maps_url"),
                    }
                    break

    return {
        "driver": driver,
        "date": frappe.utils.today(),
        "trip_count": len(worker_trips),
        "stop_count": stop_count,
        "expected_total": expected_total,
        "next_pickup": next_pickup,
    }

WORKER_REQUEST_CATEGORIES = (
    "Maintenance",
    "Cleaning",
    "AC",
    "Plumbing",
    "Electrical",
    "Water",
    "Pest Control",
    "Custody",
    "Complaint",
    "Suggestion",
    "Other",
)

WORKER_ISSUE_LOCATIONS = (
    "Room",
    "Bathroom",
    "Kitchen",
    "Common Area",
    "Entrance",
    "Staircase",
    "External Area",
    "Other",
)

WORKER_PREFERRED_LANGUAGES = ("English", "Arabic", "Urdu", "Hindi", "Bengali")

_ENUM_SOURCES = {
    "status": ("Employee", "status"),
    "stayType": ("Housing Assignment", "stay_type"),
    "requestType": ("Transport Request", "request_type"),
    "transportStatus": ("Transport Request", "status"),
    "requestCategory": ("Resident Request", "request_category"),
    "requestStatus": ("Resident Request", "status"),
    "priority": ("Resident Request", "priority"),
    "issueLocation": ("Resident Request", "issue_location"),
}

@frappe.whitelist(allow_guest=True)
@rate_limit(limit=30, seconds=60)
def get_enum_labels(lang="ar"):
    """Localized labels for the worker portal's server enums (read, no identity).

    Single source of truth for the Masar Select-option translations: for each enum
    namespace the SPA renders, this reads the field's LIVE Select options from
    ``frappe.get_meta`` and maps each English value to its translation from the
    app's translation files (``ar.csv``) via ``frappe.translate.get_all_translations``. The
    portal then needs no hand-maintained JS enum map — a new or renamed option is
    picked up automatically, and the one place a label is authored is the CSV, so
    the two can never drift (the recurring "English leaks into the Arabic UI"
    class). The stored value stays English for round-trip; only the label is
    localized.

    Returns ``{namespace: {english_value: localized_label}}``. Only entries whose
    translation differs from the raw value are included (English mode renders the
    raw value, so identity entries add nothing). Public + cacheable: it exposes no
    worker data, only option metadata + translations, so no token is required."""
    lang = (lang or "ar").strip() or "ar"
    from frappe.translate import get_all_translations

    translations = get_all_translations(lang) or {}
    out = {}
    for ns, (doctype, field) in _ENUM_SOURCES.items():
        meta_field = frappe.get_meta(doctype).get_field(field)
        if not meta_field or not meta_field.options:
            continue
        labels = {}
        for opt in meta_field.options.split("\n"):
            opt = opt.strip()
            if opt and translations.get(opt) and translations[opt] != opt:
                labels[opt] = translations[opt]
        if labels:
            out[ns] = labels
    return out

@frappe.whitelist(allow_guest=True)
@rate_limit(limit=60, seconds=60)
def get_worker_context(token=None):
    """The worker's own profile + document expiries (read, token-scoped).

    Resolves the token to one Employee and returns the durable identity fields the
    Masar profile screen shows. Employee field availability varies by HR setup, so
    every field is read defensively via ``.get()``; missing fields surface as None
    rather than erroring. Read-only, no commit, no GL."""
    employee = _resolve_worker(token)
    emp = frappe.get_cached_doc("Employee", employee)

    documents = _worker_documents(emp)
    photo = emp.get("image")
    return {
        "employee": emp.name,
        "employee_name": emp.get("employee_name"),
        "employee_number": emp.get("employee_number") or emp.name,
        "designation": emp.get("designation"),
        "department": emp.get("department"),
        "project": emp.get("project"),
        "company": emp.get("company"),
        "status": emp.get("status"),
        "date_of_joining": _fmt_date(emp.get("date_of_joining")),
        "cell_number": emp.get("cell_number") or emp.get("personal_email"),
        "photo": photo,
        "documents": documents,
        "realtime_room": portal_room(WORKER, token),
    }

@frappe.whitelist(allow_guest=True)
@rate_limit(limit=60, seconds=60)
def get_worker_accommodation(token=None):
    """The worker's active accommodation (read, token-scoped).

    Resolves the token to one Employee and returns their current housing —
    building, room, bed, occupancy, the building in-charge contact, and any
    building notices. Scoped to the resolved employee; a worker with no active
    assignment gets a friendly ``{"assignment": None}`` empty state. Read-only."""
    from apex.apex_core.utils.addresses import get_address_text

    employee = _resolve_worker(token)
    assignment = _active_assignment(employee)
    if not assignment:
        return {"assignment": None}

    building = None
    if assignment.get("building"):
        b = frappe.db.get_value(
            "Building",
            assignment["building"],
            [
                "name",
                "building_name",
                "city",
                "district",
                "site",
                "google_maps_url",
                "responsible_supervisor",
                "current_occupants",
                "total_capacity",
            ],
            as_dict=True,
        )
        if b:
            in_charge = None
            user = b.get("responsible_supervisor")
            if user:
                in_charge = {
                    "name": frappe.utils.get_fullname(user) or user,
                    "phone": frappe.db.get_value("User", user, "mobile_no"),
                }
            _addr = get_address_text("Site", b.get("site")) or get_address_text(
                "Building", assignment["building"]
            )
            building = {
                "name": b.get("name"),
                "building_name": b.get("building_name"),
                "city": b.get("city"),
                "district": b.get("district"),
                "address": _addr,
                "google_maps_url": b.get("google_maps_url"),
                "current_occupants": b.get("current_occupants"),
                "total_capacity": b.get("total_capacity"),
                "in_charge": in_charge,
            }

    room = None
    if assignment.get("room"):
        r = frappe.db.get_value(
            "Room",
            assignment["room"],
            ["name", "room_number", "floor", "room_type", "bed_capacity", "current_occupancy"],
            as_dict=True,
        )
        room = r or None

    bed = None
    if assignment.get("bed"):
        bd = frappe.db.get_value(
            "Bed", assignment["bed"], ["name", "bed_code", "status"], as_dict=True
        )
        bed = bd or None

    return {
        "assignment": {
            "name": assignment["name"],
            "check_in_date": _fmt_date(assignment.get("check_in_date")),
            "stay_type": assignment.get("stay_type"),
            "expected_checkout_date": _fmt_date(assignment.get("expected_checkout_date")),
            "notes": assignment.get("notes"),
        },
        "building": building,
        "room": room,
        "bed": bed,
    }

def _live_trips_by_request(request_names, status_map):
    """The dispatched trip for each request that has no stored link yet, in ONE read.

    ``Transport Request.dispatch_trip`` is stamped only at fulfilment, so during the
    en-route window — the exact moment a worker opens the screen — the link is empty
    and the trip has to be resolved from the trip's own back-link. Resolving it per
    row is one query per request; resolving the whole set is one query total, and the
    status rides along in the same read so those rows cost nothing extra either.

    ``status_map`` is filled in place for the trips found here, so a caller holding
    both maps can answer every row's status without another read.
    """
    live = {}
    if not request_names:
        return live
    for dt in frappe.get_all(
        "Dispatch Trip",
        filters={
            "transport_request": ["in", request_names],
            "status": "Dispatched",
            "docstatus": ["<", 2],
        },
        fields=["name", "transport_request", "status"],
    ):
        live[dt["transport_request"]] = dt["name"]
        status_map[dt["name"]] = dt["status"]
    return live

def _trip_status(dispatch_trip, status_map):
    """The Dispatch Trip status, taken from the batches the caller already fetched.

    Membership is tested rather than truthiness because a trip with a null status is
    in the batch and must not be re-read. A trip absent from both batches is a row
    neither read covers, and it falls back to a single read rather than reporting a
    status the endpoint never established.
    """
    if not dispatch_trip:
        return None
    if dispatch_trip in status_map:
        return status_map[dispatch_trip]
    return frappe.db.get_value("Dispatch Trip", dispatch_trip, "status")

@frappe.whitelist(allow_guest=True)
@rate_limit(limit=60, seconds=60)
def get_worker_transport(token=None):
    """The worker's shuttle(s), split into upcoming vs past (read, token-scoped).

    Resolves the token to one Employee and returns the transport requests that
    carry them — pickup point + time, the ordered route stops, and (when
    dispatched) the assigned vehicle/plate and driver name/contact. Scoped to the
    resolved employee via the Transport Request worker manifest; a worker on no
    live request gets empty lists. Read-only, no GL.

    Each trip is tagged ``is_upcoming`` against ``now_datetime()`` (the
    SAME predicate Home's next_ride uses), and the trips are partitioned into
    ``upcoming`` and ``past`` so the Transport screen can never present a trip
    that already departed as if it were the next ride — Home and Transport stay
    in lock-step. ``trips`` is kept as an alias of ``upcoming`` for backward
    compatibility with any caller that read the old flat list.

    Each trip also carries its ``boarding_window`` — the five-state verdict on the
    worker's OWN pickup stop (``boarding_window.resolve``) — so the screen renders
    the state the ride is actually in instead of offering a confirm button the
    server would refuse."""
    employee = _resolve_worker(token)
    requests = _worker_transport_requests(employee)
    now_dt = frappe.utils.now_datetime()
    assignment = _active_assignment(employee)
    my_building = assignment.get("building") if assignment else None

    lookups = _transport_lookups(requests, employee)

    upcoming = []
    past = []
    for req in requests:
        trip = _transport_trip(req, lookups, my_building, now_dt)
        (upcoming if trip["is_upcoming"] else past).append(trip)

    past.reverse()
    return {
        "date": frappe.utils.today(),
        "upcoming": upcoming,
        "past": past,
        "trips": upcoming,
    }

def _transport_lookups(requests, employee):
    """Reads every vehicle, driver, trip and rating the request list refers to, in one pass each."""
    vehicle_names = {r["assigned_vehicle"] for r in requests if r.get("assigned_vehicle")}
    driver_names = {r["assigned_driver"] for r in requests if r.get("assigned_driver")}
    trip_names = {r["dispatch_trip"] for r in requests if r.get("dispatch_trip")}

    vehicle_map = {}
    if vehicle_names:
        for v in frappe.get_all(
            "Salis Vehicle",
            filters={"name": ["in", list(vehicle_names)]},
            fields=["name", "plate_number", "vehicle_category"],
        ):
            vehicle_map[v["name"]] = v

    driver_map = {}
    if driver_names:
        for d in frappe.get_all(
            "Salis Driver",
            filters={"name": ["in", list(driver_names)]},
            fields=["name", "full_name", "phone"],
        ):
            driver_map[d["name"]] = {"full_name": d["full_name"], "phone": d["phone"]}

    depart_map = {}
    status_map = {}
    if trip_names:
        for dt in frappe.get_all(
            "Dispatch Trip",
            filters={"name": ["in", list(trip_names)]},
            fields=["name", "depart_time", "status"],
        ):
            depart_map[dt["name"]] = dt["depart_time"]
            status_map[dt["name"]] = dt["status"]

    rated_trips = set()
    if trip_names:
        rated_trips = set(
            frappe.get_all(
                "Transport Trip Rating",
                filters={"employee": employee, "dispatch_trip": ["in", list(trip_names)]},
                pluck="dispatch_trip",
            )
        )

    return {
        "vehicle": vehicle_map,
        "driver": driver_map,
        "depart": depart_map,
        "status": status_map,
        "live": _live_trips_by_request(
            [r["name"] for r in requests if not r.get("dispatch_trip")], status_map
        ),
        "rated": rated_trips,
    }

def _transport_trip(req, lookups, my_building, now_dt):
    """Shapes one Transport Request into the trip the Transport screen renders."""
    is_upcoming = _is_upcoming_pickup(req.get("pickup_datetime"), now_dt)
    dispatch_trip = req.get("dispatch_trip") or lookups["live"].get(req["name"])
    stops = (
        _ordered_trip_stops(dispatch_trip, req.get("route_plan"))
        if dispatch_trip
        else _ordered_stops(req.get("route_plan"))
    )
    my_pickup = _worker_pickup_stop(stops, my_building)

    return {
        "transport_request": req["name"],
        "dispatch_trip": dispatch_trip,
        "request_type": req.get("request_type"),
        "status": req.get("status"),
        "trip_status": _trip_status(dispatch_trip, lookups["status"]),
        "pickup_point": req.get("pickup_point"),
        "pickup_datetime": (
            frappe.utils.cstr(req["pickup_datetime"]) if req.get("pickup_datetime") else None
        ),
        "depart_time": (
                _fmt_time(lookups["depart"].get(dispatch_trip))
                if dispatch_trip
                else None
        ),
        "is_upcoming": is_upcoming,
        "has_rated": bool(
            dispatch_trip
            and not is_upcoming
            and dispatch_trip in lookups["rated"]
        ),
        "boarding_window": boarding_window.resolve(
            dispatch_trip,
            req["name"],
            (my_pickup or {}).get("accommodation_building") or req.get("accommodation_building"),
            now=now_dt,
        ),
        "stops": stops,
        "my_pickup": my_pickup,
        "destination": _route_destination_stop(stops, my_pickup),
        "maps_route_url": _full_route_maps_url(stops),
        "vehicle": (
            lookups["vehicle"].get(req["assigned_vehicle"]) if req.get("assigned_vehicle") else None
        ),
        "driver": (
            lookups["driver"].get(req["assigned_driver"]) if req.get("assigned_driver") else None
        ),
    }

@frappe.whitelist(allow_guest=True)
@rate_limit(limit=60, seconds=60)
def list_worker_requests(token=None):
    """The worker's own Accommodation Resident Requests (read, token-scoped).

    Resolves the token to one Employee and returns the requests they raised —
    reusing the native Accommodation Resident Request channel (no separate
    ticketing engine). Scoped by ``employee``; cannot return another worker's
    requests. Read-only."""
    employee = _resolve_worker(token)
    rows = frappe.get_all(
        "Resident Request",
        filters={"employee": employee},
        fields=[
            "name",
            "request_category",
            "priority",
            "issue_location",
            "description",
            "status",
            "resolution_notes",
            "target_doctype",
            "target_document",
            "creation",
        ],
        order_by="creation desc",
        limit=50,
    )
    for r in rows:
        r["creation"] = frappe.utils.cstr(r.get("creation"))
    return rows

@frappe.whitelist(allow_guest=True)
@rate_limit(limit=60, seconds=60)
def get_worker_request_detail(token=None, name=None):
    """One of the worker's OWN resident requests, in full (read, token-scoped).

    Resolves the token to a single Employee via ``_resolve_worker`` (the only
    place identity is established), then fetches the Accommodation Resident
    Request named ``name`` ONLY IF its ``employee`` equals that resolved worker —
    the EXACT same ownership filter ``list_worker_requests`` uses. The lookup is
    a single ``frappe.db.get_value`` keyed on BOTH ``name`` AND
    ``employee=<resolved>``: a request belonging to any other worker simply does
    not match and yields no row, at which point we raise
    ``frappe.PermissionError``. The client-supplied ``name`` is therefore never
    trusted on its own — it can only ever address the token-owner's own rows, so
    this endpoint cannot read another worker's request.

    Returns the request's status, a reconstructed created -> current status
    timeline (the DocType has no status-history child table, so it is built from
    creation/modified/closed_on), the triage and resolution notes, the
    category/priority/location/description, and the attachment file url if any.
    Read-only, no commit, no GL."""
    employee = _resolve_worker(token)

    name = (name or "").strip()
    if not name:
        frappe.throw(_("A request reference is required."), frappe.PermissionError)

    req = frappe.db.get_value(
        "Resident Request",
        {"name": name, "employee": employee},
        [
            "name",
            "request_category",
            "priority",
            "issue_location",
            "description",
            "status",
            "triage_notes",
            "resolution_notes",
            "attachment",
            "creation",
            "modified",
            "closed_on",
        ],
        as_dict=True,
    )
    if not req:
        frappe.throw(
            _("This request is not available or does not belong to you."),
            frappe.PermissionError,
        )

    attachment_url = None
    if req.get("attachment"):
        attachment_url = frappe.utils.get_url(req["attachment"])

    return {
        "name": req["name"],
        "status": req.get("status"),
        "request_category": req.get("request_category"),
        "priority": req.get("priority"),
        "issue_location": req.get("issue_location"),
        "description": req.get("description"),
        "triage_notes": req.get("triage_notes"),
        "resolution_notes": req.get("resolution_notes"),
        "attachment": attachment_url,
        "creation": frappe.utils.cstr(req.get("creation")) if req.get("creation") else None,
        "modified": frappe.utils.cstr(req.get("modified")) if req.get("modified") else None,
        "closed_on": frappe.utils.cstr(req.get("closed_on")) if req.get("closed_on") else None,
        "timeline": _request_status_timeline(req),
    }

@frappe.whitelist(allow_guest=True)
@rate_limit(limit=60, seconds=60)
def get_worker_custody(token=None):
    """The custody articles the worker currently holds (read, token-scoped).

    Resolves the token to one Employee and returns their live custody holding,
    derived from the read-only Accommodation Stock Ledger — the same net-balance
    source as the ``Accommodation Stock Balance`` report, not a Custody Issue
    replay. Balance per (building, article) is the signed sum of non-cancelled
    custody-article ledger rows for THIS employee (issues add, returns reverse),
    so the net is what is still out. A worker who moved buildings still sees
    prior custody. Scoped strictly to the resolved employee; a client-supplied
    id can never widen it. Zero/negative-net rows are dropped.

    For each still-held item the worker view surfaces what matters to them — not
    money: the ``received_date`` (posting date of the latest issue row), the
    ``issued_by`` supervisor (the source Custody Issue's owner, resolved to a
    full name; falls back to the building's responsible supervisor, else None),
    and the ``building``. Read-only, no commit, no GL."""
    employee = _resolve_worker(token)

    rows = frappe.get_all(
        "Accommodation Stock Ledger",
        filters={
            "is_cancelled": 0,
            "item_type": "Custody Article",
            "employee": employee,
        },
        fields=[
            "building",
            "item",
            "item_name",
            "uom",
            "signed_qty",
            "posting_date",
            "voucher_type",
            "voucher_no",
        ],
        order_by="posting_date asc, creation asc",
    )

    items = _net_custody_items(rows)
    for bucket in items:
        bucket["issued_by"] = _custody_issued_by(bucket.pop("_issue_voucher"), bucket["building"])

    items.sort(key=lambda d: (d["item_name"] or d["item"] or "", d["building"] or ""))
    return {"items": items}

@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=10, seconds=60 * 60)
def create_worker_request(
    token=None,
    category=None,
    subject=None,
    body=None,
    priority=None,
    issue_location=None,
    preferred_language=None,
    photo=None,
    photo_filename=None,
):
    """Raise an Accommodation Resident Request for the worker (write, token-scoped).

    Reuses the native resident-request channel rather than inventing a ticketing
    engine. The employee, building, room and bed are taken from the worker's
    resolved identity + active assignment — NEVER from the client — so a request
    can only ever be filed for the token's own worker, against their own housing.
    Inserts a single ``source_channel = QR Web Form`` request as ``requester_type
    = Worker``; posts no GL. ``subject`` is folded into the description (the native
    DocType has no subject field).

    The worker may additionally set ``issue_location`` and ``preferred_language``
    (each validated against the DocType's Select options; an out-of-set value is
    simply dropped, since both fields are optional) and attach a single ``photo``
    (a base64 image persisted server-side as a private File on the new request via
    ``_attach_worker_photo`` — no separate guest upload endpoint is exposed)."""
    employee = _resolve_worker(token)

    category = (category or "Other").strip()
    if category not in WORKER_REQUEST_CATEGORIES:
        category = "Other"
    priority = (priority or "Low").strip()
    if priority not in ("Low", "Medium", "High", "Critical"):
        priority = "Low"

    issue_location = (issue_location or "").strip()
    if issue_location not in WORKER_ISSUE_LOCATIONS:
        issue_location = None
    preferred_language = (preferred_language or "").strip()
    if preferred_language not in WORKER_PREFERRED_LANGUAGES:
        preferred_language = None

    subject = (subject or "").strip()
    body = (body or "").strip()
    if not body and not subject:
        frappe.throw(_("Please describe your request."))
    description = body if not subject else (f"{subject}\n\n{body}" if body else subject)

    assignment = _active_assignment(employee)
    building = room = bed = None
    if assignment:
        building = assignment.get("building")
        room = assignment.get("room")
        bed = assignment.get("bed")

    doc = frappe.get_doc(
        {
            "doctype": "Resident Request",
            "source_channel": "QR Web Form",
            "requester_type": "Worker",
            "employee": employee,
            "worker_name": frappe.db.get_value("Employee", employee, "employee_name"),
            "building": building,
            "room": room,
            "bed": bed,
            "no_active_assignment": 0 if assignment else 1,
            "request_category": category,
            "priority": priority,
            "issue_location": issue_location,
            "preferred_language": preferred_language,
            "description": description,
            "status": "New",
        }
    )
    with as_capacity(WORKER):
        doc.insert()
    if photo:
        _attach_worker_photo(doc, photo, photo_filename)
    return {"name": doc.name, "status": doc.status}


_RESIDENT_REQUEST_CLOSED_STATES = ("Resolved", "Rejected", "Closed")


def _rating_stars() -> int:
    """How many stars a Transport Trip Rating is out of.

    Read from the field's own ``options``, which is the same number the desk
    multiplies the stored fraction by to draw the stars
    (frappe/public/js/frappe/form/controls/rating.js:99-101); a second copy here
    would let the portal's scale and the desk's drift apart. Frappe's own default
    applies when ``options`` is unset.
    """
    field = frappe.get_meta("Transport Trip Rating").get_field("rating")
    return cint(field.options) or 5


def _alert_lead(fieldname: str, fallback: int) -> int:
    """Days of notice for one Masar alert window, read from Salis Settings.

    The fallback applies to an unset or zero field, which is what a Single
    returns before an operator has ever opened it; a site that means "no notice"
    turns the alert off at its own switch, never by zeroing the window.
    """
    return cint(frappe.db.get_single_value("Salis Settings", fieldname)) or fallback


@frappe.whitelist(allow_guest=True)
@rate_limit(limit=60, seconds=60)
def get_worker_home(token=None):
    """The worker's composed home/today screen (read, token-scoped).

    Resolves the token to one Employee and folds four already-exposed worker
    surfaces into a single "today" payload, so the home screen makes one call:

      * ``profile_alerts``    — the profile's own document items
        (``get_worker_context``) filtered to those expiring soon (``days_left``
        at or under the Habitat renewal lead) or already past; a list, possibly
        empty.
      * ``next_ride``         — the single soonest upcoming shuttle: the head of
        ``get_worker_transport``'s ``upcoming`` partition (same now_datetime()
        pivot Transport uses, so the two screens never contradict), or None.
      * ``bed``               — the worker's current accommodation bed from
        ``get_worker_accommodation``, ENRICHED with its building + room + check-in
        so the Home chip reads as a real location, not a bare bed code; or None.
      * ``open_request_count`` — count of the worker's own resident requests
        (``list_worker_requests``) not in a settled state.
      * ``iqama_days_left``    — whole days until the Iqama expires (or None),
        surfaced for the Home glance tile regardless of the alert window.

    Purely additive: it composes the existing token-scoped endpoints (each
    re-resolves the same token via ``_resolve_worker``) and changes none of
    them. Read-only, no commit, no GL."""
    _resolve_worker(token)

    profile = get_worker_context(token)
    documents = profile.get("documents") or []
    profile_alerts = [
        d
        for d in documents
        if d.get("days_left") is not None and d["days_left"] <= _alert_lead("worker_document_alert_lead_days", 60)
    ]
    iqama_days_left = next(
        (d.get("days_left") for d in documents if d.get("type") == "iqama"),
        None,
    )

    transport = get_worker_transport(token)
    upcoming = transport.get("upcoming") or []
    next_ride = upcoming[0] if upcoming else None

    acc = get_worker_accommodation(token)
    bed = acc.get("bed")
    if bed:
        b = acc.get("building") or {}
        r = acc.get("room") or {}
        asg = acc.get("assignment") or {}
        bed = {
            **bed,
            "building": b.get("name"),
            "building_name": b.get("building_name"),
            "room": r.get("name"),
            "room_number": r.get("room_number"),
            "floor": r.get("floor"),
            "check_in_date": asg.get("check_in_date"),
        }

    custody = get_worker_custody(token)
    requests = list_worker_requests(token)
    open_request_count = sum(
        1
        for r in requests
        if r.get("status") not in _RESIDENT_REQUEST_CLOSED_STATES
    )

    return {
        "date": frappe.utils.today(),
        "profile": profile,
        "accommodation": acc,
        "custody": custody,
        "transport": transport,
        "requests": requests,
        "profile_alerts": profile_alerts,
        "next_ride": next_ride,
        "bed": bed,
        "open_request_count": open_request_count,
        "iqama_days_left": iqama_days_left,
    }

@frappe.whitelist(allow_guest=True)
@rate_limit(limit=60, seconds=60)
def get_worker_contacts(token=None):
    """The worker's key contacts for the Masar home (read, token-scoped).

    Resolves the token to one Employee and returns the three contacts the home
    My Contacts card shows: the building in-charge (from the active assignment's
    building), today's driver (from the worker's own today Dispatch Trip), and the
    housing office number (from Habitat Settings). Each is None/absent when not set,
    so the card degrades cleanly. Scoped to the resolved employee; read-only, no GL."""
    employee = _resolve_worker(token)
    return {
        "building_in_charge": _building_in_charge(employee),
        "today_driver": _today_driver(employee),
        "housing_office_number": frappe.db.get_single_value(
            "Habitat Settings", "housing_office_number"
        )
        or None,
    }


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=6, seconds=60 * 60)
def notify_hr_iqama_expiring(token=None):
    """One-tap: notify HR that the worker's Iqama is expiring (write, token-scoped).

    Resolves the token to one Employee via ``_resolve_worker`` (the only place
    identity is established — the client never supplies a worker id), re-reads
    that Employee's Iqama number + expiry SERVER-SIDE, and recomputes
    ``days_left``. The HR notification is raised ONLY when the Iqama is genuinely
    inside the action window (``days_left`` is known and <=
    ``Salis Settings.iqama_notify_hr_lead_days``); a worker whose Iqama is comfortably
    valid, or
    has no expiry on file, is a silent no-op (``{"notified": False}``) — the
    client cannot force an alert by faking the threshold.

    When in window, posts a native in-app ``Notification Log`` (type Alert) to the
    HR inbox (HR Manager, fallback System Manager) — the SAME channel
    ``temporary_worker_engine._notify_hr`` uses; no separate ticketing engine, no
    GL. Tight ``rate_limit`` so the personal link cannot spam HR.
    Returns ``{"notified": bool, "days_left": int|None, "recipients": int}``."""
    employee = _resolve_worker(token)
    emp = frappe.get_cached_doc("Employee", employee)

    iqama_no, iqama_expiry = _iqama_of(emp)
    days_left = _days_until(iqama_expiry)

    if days_left is None or days_left > _alert_lead("iqama_notify_hr_lead_days", 30):
        return {"notified": False, "days_left": days_left, "recipients": 0}

    worker_name = emp.get("employee_name") or employee
    emp_no = emp.get("employee_number") or employee
    if days_left < 0:
        subject = _("Iqama EXPIRED — {0} ({1}) requests HR action").format(worker_name, emp_no)
    else:
        subject = _("Iqama expiring in {0} day(s) — {1} ({2}) requests HR action").format(
            days_left, worker_name, emp_no
        )
    message = _(
        "{0} (Employee {1}) used the Masar worker portal to flag that their Iqama "
        "{2} is expiring (expiry {3}, {4} day(s) left). Please action the renewal."
    ).format(worker_name, emp_no, iqama_no or _("on file"), _fmt_date(iqama_expiry), days_left)

    recipients = role_holders_escalating("HR Manager", "System Manager")
    for user in recipients:
        notify_user_system(
            user,
            subject,
            message,
            document_type="Employee",
            document_name=employee,
        )

    return {"notified": True, "days_left": days_left, "recipients": len(recipients)}

_WORKER_BOARDING_METHOD = "Worker"

def _get_or_create_trip_log(dispatch_trip, employee=None):
    """The trip's open (draft) Trip Start Log, created if none exists yet — the
    same get-or-create the driver QR scan uses (salis/api/boarding.py), so a
    worker self-confirm and a driver scan append to ONE shared log. A
    submitted/cancelled log is not reused; a fresh draft is opened so a
    post-submission confirm never mutates a closed record.

    ``employee`` is the resolved worker a fresh create is authorised under: the log is
    the driver's, so the create runs inside ``as_capacity(WORKER, employee)`` and
    ``_trip_start_log_capacity_verdict`` checks the employee against the trip's manifest
    rather than any field on the row itself.

    Two callers can reach this at once — a driver scan and a worker self-confirm — and
    each would otherwise see no log and create one. The Dispatch Trip row is locked
    FIRST, by this function rather than by whatever called it, so the two serialise on
    a row that always exists; the existence read that follows is itself a locking read,
    which returns the latest committed row rather than this transaction's pre-lock
    snapshot. Under REPEATABLE READ a plain read here answers from that snapshot, so
    the second caller sees no log, creates a second one, and both report success.
    """
    frappe.db.get_value("Dispatch Trip", dispatch_trip, "name", for_update=True)
    existing = frappe.db.get_value(
        "Trip Start Log",
        {"dispatch_trip": dispatch_trip, "docstatus": 0},
        "name",
        for_update=True,
    )
    if existing:
        return frappe.get_doc("Trip Start Log", existing)
    log = frappe.get_doc(
        {
            "doctype": "Trip Start Log",
            "dispatch_trip": dispatch_trip,
            "status": "Started",
            "start_datetime": frappe.utils.now_datetime(),
        }
    )
    with as_capacity(WORKER, employee):
        log.insert()
    from apex.salis.api.boarding_flow import ensure_trip_boarding_state

    ensure_trip_boarding_state(dispatch_trip)
    return log

@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=12, seconds=60 * 60)
def confirm_boarding(token=None, transport_request=None):
    """"I'm at the pickup": the worker self-confirms boarding (write, token-scoped).

    Resolves the token to one Employee via ``_resolve_worker`` (the sole place
    identity is established — the client never supplies a worker id), finds that
    worker's relevant today's Dispatch Trip from their OWN manifest membership,
    and appends a ``method = Worker`` Trip Boarding Event for THIS worker onto the
    trip's draft Trip Start Log — the SAME child table + get-or-create log the
    driver QR scan writes, so the two paths share one boarding manifest.

    Gated on the worker's OWN stop, not on the calendar day: the confirm is accepted
    only while ``boarding_window`` puts that stop in ``at_stop``, and is refused with
    a named reason — before the trip is locked and before any log exists — when the
    bus has not reached it, has already left it, or the trip is over. A refusal
    writes nothing at all.

    Strictly token-scoped: the boarding row is always written for the resolved
    employee, and the optional ``transport_request`` can only narrow the worker's
    own trip set (an id they are not registered on does not match). Re-confirming
    is idempotent — a worker already on the manifest yields no second row
    (``created = False``). A bad/blank/disabled token fails closed
    (PermissionError) before any write; a worker with no boardable trip today is a
    clean no-op (``{"trip": None}``). Posts no GL.

    Returns ``{"created": bool, "dispatch_trip": str|None, "trip_start_log":
    str|None, "boarded_count": int|None, "boarding_window": dict}``;
    ``{"trip": None}`` when nothing is boardable today."""
    employee = _resolve_worker(token)
    transport_request = (transport_request or "").strip() or None

    resolved = _worker_today_dispatch_trip(employee, transport_request)
    if not resolved:
        return {"trip": None, "created": False}
    dispatch_trip, request_name, stop_name, building = resolved

    window = boarding_window.resolve(dispatch_trip, request_name, building)
    boarding_window.validate_window_is_open(window)

    frappe.db.get_value("Dispatch Trip", dispatch_trip, "name", for_update=True)

    log = _get_or_create_trip_log(dispatch_trip, employee)

    if already_boarded(log, employee):
        return {
            "created": False,
            "dispatch_trip": dispatch_trip,
            "transport_request": request_name,
            "trip_start_log": log.name,
            "boarded_count": log.boarded_count,
            "boarding_window": window,
        }

    log.append(
        "boarding_events",
        {
            "worker": employee,
            "stop_name": stop_name,
            "accommodation_building": building,
            "boarded_at": frappe.utils.now_datetime(),
            "method": _WORKER_BOARDING_METHOD,
        },
    )
    with as_capacity(WORKER, employee):
        log.save()
    from apex.salis.api.boarding_flow import mark_boarded

    mark_boarded(dispatch_trip, employee)
    return {
        "created": True,
        "dispatch_trip": dispatch_trip,
        "transport_request": request_name,
        "trip_start_log": log.name,
        "boarded_count": log.boarded_count,
        "boarding_window": window,
    }

@frappe.whitelist(allow_guest=True)
@rate_limit(limit=60, seconds=60)
def get_worker_boarding_pass(token=None, transport_request=None):
    """The worker's own signed QR boarding pass for today's trip (read, token-scoped).

    The driver scanner (salis/api/boarding.py) validates a per-(trip, worker)
    HMAC-signed token; the same signed payload is what the worker shows as a QR for
    the driver to scan. Here the worker resolves to a single Employee from their
    token and the trip is resolved FORWARD from their own manifest membership (the
    same ``_worker_today_dispatch_trip`` boarding self-confirm uses) — the client
    never supplies a trip or worker id, so a pass can only ever be issued for the
    token's own worker on a trip they are actually on. Reuses ``boarding._issue_token``
    so the worker's QR and the driver's scanner share ONE signing scheme; issues no
    DB write (a pass is just a signed claim). ``{"pass": None}`` when the worker has
    no boardable trip today."""
    from apex.salis.api import boarding

    employee = _resolve_worker(token)
    transport_request = (transport_request or "").strip() or None

    resolved = _worker_today_dispatch_trip(employee, transport_request)
    if not resolved:
        return {"pass": None}
    dispatch_trip, request_name, stop_name, building = resolved

    route_plan = frappe.db.get_value("Dispatch Trip", dispatch_trip, "route_plan")
    if not route_plan:
        route_plan = frappe.db.get_value("Transport Request", request_name, "route_plan")
    stops = _ordered_trip_stops(dispatch_trip, route_plan)
    my_pickup = _worker_pickup_stop(stops, building)
    destination = _route_destination_stop(stops, my_pickup)
    pickup_label = (
        (my_pickup.get("pickup") or {}).get("building_name")
        or my_pickup.get("accommodation_building")
        or my_pickup.get("stop_name")
        if my_pickup
        else None
    )
    destination_label = (
        destination.get("location") or destination.get("stop_name") if destination else None
    )

    pass_token = boarding._issue_token(dispatch_trip, employee)
    return {
        "pass": {
            "qr_payload": pass_token,
            "dispatch_trip": dispatch_trip,
            "transport_request": request_name,
            "stop_name": stop_name,
            "pickup_label": pickup_label,
            "destination_label": destination_label,
            "holder_name": frappe.db.get_value("Employee", employee, "employee_name"),
            "expires_in_hours": boarding.PASS_TTL_HOURS,
        }
    }

_WORKER_TRANSPORT_SERVICE_REQUEST_TYPE = {
    "Site Transport": "Accommodation to Project Shuttle",
    "Inter-City Relocation": "Inter-City Relocation",
}

@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=6, seconds=60 * 60)
def create_worker_transport_request(
    token=None,
    service_line=None,
    from_location=None,
    to_location=None,
    pickup_datetime=None,
    purpose=None,
    adhoc_passengers=None,
):
    """Raise a Transport Request for the worker (write, token-scoped).

    Reuses the native Transport Request channel (no parallel intake DocType). The
    worker resolves to one Employee from their token (the sole identity source — the
    client never supplies a worker id); that worker is ALWAYS added to the request's
    registered manifest, and their active accommodation building + project seed the
    request, so a request can only ever be filed for the token's own worker. The
    worker may additionally list ad-hoc (unregistered) co-passengers — each a
    name+ID(+expiry) row kept in a SEPARATE ``adhoc_passengers`` table so they stay
    distinguishable from registered workers. ``service_line`` is constrained to the
    two worker lines and the request type is derived from it server-side. The
    request is created as a New draft (``source_channel = Masar Worker``) for the
    fleet desk to validate/schedule; posts no GL. Tight ``rate_limit`` so a personal
    link cannot spam the desk."""
    employee = _resolve_worker(token)

    service_line = (service_line or "Site Transport").strip()
    if service_line not in _WORKER_TRANSPORT_SERVICE_REQUEST_TYPE:
        service_line = "Site Transport"
    request_type = _WORKER_TRANSPORT_SERVICE_REQUEST_TYPE[service_line]

    from_location = (from_location or "").strip()[:140] or None
    to_location = (to_location or "").strip()[:140] or None
    purpose = (purpose or "").strip()
    if purpose and len(purpose) > 2000:
        frappe.throw(_("Purpose is too long. Please keep it under 2000 characters."))
    if not purpose and not to_location:
        frappe.throw(_("Please describe where you need to go."))

    pickup_datetime = (pickup_datetime or "").strip() or None
    if pickup_datetime:
        try:
            pickup_datetime = frappe.utils.get_datetime(pickup_datetime).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        except Exception:
            frappe.throw(_("The pickup date and time is not valid."))

    adhoc_rows = _clean_adhoc_passengers(adhoc_passengers)

    assignment = _active_assignment(employee)
    building = assignment.get("building") if assignment else None
    project = assignment.get("project") if assignment else None
    worker_name = frappe.db.get_value("Employee", employee, "employee_name")

    doc = frappe.get_doc(
        {
            "doctype": "Transport Request",
            "service_line": service_line,
            "request_type": request_type,
            "source_channel": "Masar Worker",
            "requester_name": worker_name,
            "accommodation_building": building if service_line == "Site Transport" else None,
            "project": project,
            "from_location": from_location,
            "to_location": to_location,
            "pickup_datetime": pickup_datetime,
            "purpose": purpose,
            "status": "New",
            "workers": [{"employee": employee, "pickup_point": from_location}],
            "adhoc_passengers": adhoc_rows,
        }
    )
    with as_capacity(WORKER):
        doc.insert()
    return {"name": doc.name, "status": doc.status, "adhoc_count": len(adhoc_rows)}

@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=10, seconds=60)
def submit_trip_rating(token=None, dispatch_trip=None, rating=None, feedback=None, transport_request=None):
    """Allows a worker to submit a rating and feedback for a completed trip.

    Scoped by the worker's token to ensure they actually went on the trip: the
    caller's identity (``employee``) is resolved here and cannot come from the
    request body. "Trip must be Completed" and "employee was on the trip" are
    pure data invariants that need no identity once ``employee`` is known, so
    they live on Transport Trip Rating's own ``validate`` (reachable from any
    insertion path, not only this endpoint) and are not repeated here.

    The portal speaks in WHOLE STARS and the field stores a FRACTION: a Frappe
    Rating holds 0-1 and the desk multiplies it by the field's ``options`` star
    count to draw it (frappe/public/js/frappe/form/controls/rating.js:99-101), so
    the star count is divided here rather than written through.
    """
    employee = _resolve_worker(token)

    if not dispatch_trip:
        frappe.throw(_("Missing Dispatch Trip reference."))

    out_of = _rating_stars()
    stars = cint(rating)
    if stars < 1 or stars > out_of:
        frappe.throw(_("Rating must be between 1 and {0}.").format(out_of))

    trip = frappe.db.get_value(
        "Dispatch Trip", dispatch_trip, ["status", "transport_request"], as_dict=True
    )
    if not trip:
        frappe.throw(_("Trip not found."), frappe.DoesNotExistError)

    existing = frappe.db.exists(
        "Transport Trip Rating",
        {"employee": employee, "dispatch_trip": dispatch_trip}
    )
    if existing:
        frappe.throw(_("You have already rated this trip."))

    doc = frappe.get_doc({
        "doctype": "Transport Trip Rating",
        "employee": employee,
        "dispatch_trip": dispatch_trip,
        "rating": stars / out_of,
        "transport_request": trip.transport_request,
        "feedback": (feedback or "").strip()[:2000]
    })
    try:
        with as_capacity(WORKER):
            doc.insert()
    except frappe.exceptions.UniqueValidationError:
        frappe.throw(_("You have already rated this trip."))
    return {"status": "success", "name": doc.name}

_PUBLIC_TRIP_FIELDS = ["name", "route_plan", "vehicle", "depart_time", "status"]

@frappe.whitelist(allow_guest=True)
@rate_limit(limit=30, seconds=60)
def get_public_trip_board():
    """Today's trips, published with no token: which vehicle, which route, when it
    leaves, and where it stands -- an arrivals-board surface anyone standing at the
    gate can read without signing in.

    Carries nothing about WHO rides. ``passengers``/``employee`` never leave the
    Route Stop / Passenger Manifest rows, and this reads only the four fields named
    above plus the stop shape (name, building, planned time) -- no phone number, no
    national id, no manifest. The personal half (my seat, my housing, my documents)
    stays behind ``get_worker_transport``/``get_worker_boarding_pass``, which still
    require a resolved token.

    ``get_all`` stays deliberate here, unpaged: the caller is Guest by design (no
    token, no employee/project to scope by), and every trip of the day must appear
    on the board or the sign is wrong for whoever is reading it at the gate.
    """
    trip_date = frappe.utils.today()
    trips = frappe.get_all(
        "Dispatch Trip",
        filters={"trip_date": trip_date, "docstatus": ["!=", 2]},
        fields=_PUBLIC_TRIP_FIELDS,
        order_by="depart_time asc, name asc",
        limit_page_length=0,
    )

    route_names = {t["route_plan"] for t in trips if t.get("route_plan")}
    route_title = (
        {
            r["name"]: r["route_name"]
            for r in frappe.get_all(
                "Route Plan", filters={"name": ["in", list(route_names)]},
                fields=["name", "route_name"],
            )
        }
        if route_names
        else {}
    )

    vehicle_ids = {t["vehicle"] for t in trips if t.get("vehicle")}
    plate_by_vehicle = (
        {
            v["name"]: v["plate_number"]
            for v in frappe.get_all(
                "Salis Vehicle", filters={"name": ["in", list(vehicle_ids)]},
                fields=["name", "plate_number"],
            )
        }
        if vehicle_ids
        else {}
    )

    board = []
    for t in trips:
        board.append(
            {
                "dispatch_trip": t["name"],
                "route_name": route_title.get(t.get("route_plan")) or t.get("route_plan"),
                "depart_time": _fmt_time(t.get("depart_time")),
                "vehicle_plate": plate_by_vehicle.get(t.get("vehicle")) or t.get("vehicle"),
                "status": t.get("status"),
                "stops": [
                    {
                        "stop_name": s.get("stop_name"),
                        "location": s.get("location"),
                        "planned_time": _fmt_time(s.get("planned_time")),
                    }
                    for s in _ordered_trip_stops(t["name"], t.get("route_plan"))
                ],
            }
        )

    return {"date": trip_date, "trips": board}
