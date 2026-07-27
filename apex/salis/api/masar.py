# Copyright (c) 2026, AFMCO and contributors
"""Masar (Worker Movement) driver-portal read APIs.

Masar is the **Workers division of Salis** — the worker-transport experience on
the shared fleet backbone. This module serves the worker-transport *trip view*
for the CURRENT driver: today's worker route, its ordered stops (the "trip road"),
and the per-stop manifest (registered workers + each stop's Habitat housing
pickup).

Driver-route endpoints resolve a presented driver credential first, then fall
back to a linked signed-in driver when no credential was presented. The client
never supplies a driver id. These route reads feed the worker view inside the
existing /driver portal and have no GL or write side effects.
"""

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit

from apex.apex_core.utils.portal_token_security import (
    WORKER,
    TOKEN_COOKIES,
    presented_token,
    resolve_portal_subject,
)
from apex.apex_core.utils.system_notify import notify_user_system
from apex.salis.api.driver_portal import _require_enabled, _resolve_driver
from apex.salis.utils import days_until as _days_until
# [#55ldxu]
from apex.salis.api.maps_links import _full_route_maps_url
from apex.salis.api.maps_links import _stop_waypoint  # noqa: F401  (re-exported)

# [#6ddse8]
WORKER_SERVICE_LINES = ("Site Transport", "Inter-City Relocation")

# [#kta0hy]
_EARTH_RADIUS_KM = 6371.0088
# [#9inje9]
_DEFAULT_FLEET_SPEED_KMPH = 40.0


def _haversine_km(lat1, lng1, lat2, lng2):
    """Great-circle distance in km between two WGS-84 points. Pure math, no I/O."""
    import math

    rlat1, rlat2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlng / 2) ** 2
    return _EARTH_RADIUS_KM * 2 * math.asin(math.sqrt(a))


def _assumed_fleet_speed_kmph():
    """Assumed average fleet speed (km/h) for the ETA, from Salis Settings via the
    zero-trap reader (a blank/0 Single value falls back to the built-in default)."""
    from apex.apex_core.doctype.salis_settings.salis_settings import get_salis_float

    return get_salis_float("assumed_fleet_speed_kmph", _DEFAULT_FLEET_SPEED_KMPH)


def _pickup_building_of(trip):
    """The Accommodation Building id the ETA targets for a worker's ride: the
    worker's OWN pickup stop's building. None when the ride has no housing pickup
    resolved (the ETA is then simply omitted)."""
    my_pickup = trip.get("my_pickup") or {}
    return my_pickup.get("accommodation_building")


def _live_dispatch_trip(transport_request):
    """The Dispatch Trip a worker's request is riding on RIGHT NOW — status
    Dispatched, driver en route. The Transport Request's own ``dispatch_trip`` link
    is stamped only at fulfilment (Completed), so during the en-route window — the
    exact time the live ETA is wanted — resolve the active trip directly by its
    back-link + live status. None when no trip is currently dispatched."""
    return frappe.db.get_value(
        "Dispatch Trip",
        {"transport_request": transport_request, "status": "Dispatched", "docstatus": ["<", 2]},
        "name",
    )


def compute_ride_eta_minutes(dispatch_trip, pickup_building):
    """Minutes until the driver reaches ``pickup_building``, from the trip's last
    stored driver GPS position — or None when the ETA cannot be computed.

    Self-contained: haversine(driver → pickup) / assumed fleet speed. Returns None
    (never raises) when the trip has no live position, the pickup building has no
    coordinates, or the speed is non-positive — the caller omits the ETA cleanly.
    Rounds to whole minutes; a driver already at the pickup yields 0."""
    if not dispatch_trip or not pickup_building:
        return None
    pos = frappe.db.get_value(
        "Dispatch Trip", dispatch_trip, ["driver_lat", "driver_lng"], as_dict=True
    )
    if not pos or pos.get("driver_lat") is None or pos.get("driver_lng") is None:
        return None
    dest = frappe.db.get_value(
        "Building", pickup_building, ["pickup_lat", "pickup_lng"], as_dict=True
    )
    if not dest or dest.get("pickup_lat") is None or dest.get("pickup_lng") is None:
        return None
    # [#1w40qu]
    if not (pos.get("driver_lat") or pos.get("driver_lng")):
        return None
    if not (dest.get("pickup_lat") or dest.get("pickup_lng")):
        return None
    speed = _assumed_fleet_speed_kmph()
    if speed <= 0:
        return None
    distance_km = _haversine_km(
        pos["driver_lat"], pos["driver_lng"], dest["pickup_lat"], dest["pickup_lng"]
    )
    return int(round((distance_km / speed) * 60))


def _fmt_time(value):
    """Render a Time field as a clean zero-padded ``HH:MM:SS`` string (or None).

    Frappe stores Time as a ``datetime.timedelta``; ``cstr`` on it yields an
    unpadded value with stray microseconds (e.g. ``6:30:00`` /
    ``2:05:46.198544``). ``format_time`` normalises it to ``06:30:00`` for a clean
    JSON payload."""
    if value in (None, ""):
        return None
    try:
        return frappe.utils.format_time(value)
    except Exception:
        return frappe.utils.cstr(value)


# [#hgsz8p]
_FINISHED_TRIP_STATUSES = frozenset({"Completed", "Cancelled"})


def _trip_date_window():
    """The trip_date filter window for "boardable now" — today AND yesterday.

    A night shift that departs before midnight runs past it: at 00:05 the trip's
    ``trip_date`` is still yesterday, so a ``trip_date = today()`` filter drops it
    at the exact moment the worker needs to board. Including yesterday keeps that
    in-progress night trip reachable. The caller drops a YESTERDAY trip that has
    already finished (see ``_drop_finished_yesterday``), so today's completed trips
    stay visible while only an in-motion night run carries over — no double-count."""
    return ["in", [frappe.utils.add_days(frappe.utils.today(), -1), frappe.utils.today()]]


def _drop_finished_yesterday(trips):
    """Drop carried-over YESTERDAY trips that are already finished.

    The yesterday half of ``_trip_date_window`` exists only to keep a night run
    still in motion reachable past midnight; a yesterday trip that has already
    Completed/Cancelled is done and must not resurface. Today's trips pass through
    untouched in every status (the driver's route view shows today's completed
    runs). Keyed on ``trip_date``, so a row missing it is kept defensively."""
    yesterday = frappe.utils.add_days(frappe.utils.today(), -1)
    return [
        t
        for t in trips
        if not (
            frappe.utils.cstr(t.get("trip_date")) == yesterday
            and t.get("status") in _FINISHED_TRIP_STATUSES
        )
    ]


def _today_worker_trips(driver):
    """Today's (and an in-progress night shift's) Dispatch Trips for ``driver``
    whose linked Transport Request is on the Workers service line. Returns a list
    of trip dicts with the route_plan and transport_request resolved, ordered by
    departure time. A trip that left before midnight is still boardable after it,
    so the date window spans yesterday+today (see ``_trip_date_window``); a
    yesterday trip that has already finished is dropped (``_drop_finished_yesterday``)."""
    trips = frappe.get_all(
        "Dispatch Trip",
        filters={
            "driver": driver,
            "trip_date": _trip_date_window(),
            "docstatus": ["<", 2],
        },
        fields=[
            "name",
            "route_plan",
            "transport_request",
            "vehicle",
            "trip_date",
            "depart_time",
            "return_time",
            "status",
        ],
        order_by="depart_time asc",
    )
    trips = _drop_finished_yesterday(trips)
    if not trips:
        return []
    # [#popsyt]
    rp_ids = {t["route_plan"] for t in trips if not t.get("transport_request") and t.get("route_plan")}
    if rp_ids:
        rp_tr = {
            r["name"]: r["transport_request"]
            for r in frappe.get_all(
                "Route Plan",
                filters={"name": ["in", list(rp_ids)]},
                fields=["name", "transport_request"],
            )
        }
        for t in trips:
            if not t.get("transport_request") and t.get("route_plan"):
                t["transport_request"] = rp_tr.get(t["route_plan"])

    tr_ids = {t["transport_request"] for t in trips if t.get("transport_request")}
    service_lines = (
        {
            r["name"]: r["service_line"]
            for r in frappe.get_all(
                "Transport Request",
                filters={"name": ["in", list(tr_ids)]},
                fields=["name", "service_line"],
            )
        }
        if tr_ids
        else {}
    )
    return [t for t in trips if service_lines.get(t.get("transport_request")) in WORKER_SERVICE_LINES]


def _registered_workers(transport_request):
    """The registered worker manifest for a Transport Request: each row's Employee
    plus the human-readable pickup point recorded on the request."""
    if not transport_request:
        return []
    rows = frappe.get_all(
        "Transport Request Worker",
        filters={"parent": transport_request, "parenttype": "Transport Request"},
        fields=["employee", "pickup_point", "notes"],
        order_by="idx asc",
    )
    # [#c1mexk]
    emp_ids = {r["employee"] for r in rows if r.get("employee")}
    emp_names = (
        {
            e["name"]: e["employee_name"]
            for e in frappe.get_all(
                "Employee", filters={"name": ["in", list(emp_ids)]}, fields=["name", "employee_name"]
            )
        }
        if emp_ids
        else {}
    )
    workers = []
    for r in rows:
        workers.append(
            {
                "employee": r.get("employee"),
                "employee_name": (emp_names.get(r["employee"]) if r.get("employee") else None),
                "pickup_point": r.get("pickup_point"),
                "notes": r.get("notes"),
            }
        )
    return workers


def _ordered_stops(route_plan):
    """The ordered Route Stop rows for a Route Plan, each enriched with its Habitat
    pickup (Accommodation Building) details when the stop is a housing pickup."""
    if not route_plan:
        return []
    rows = frappe.get_all(
        "Route Stop",
        filters={"parent": route_plan, "parenttype": "Route Plan"},
        fields=[
            "name",
            "idx",
            "stop_name",
            "accommodation_building",
            "location",
            "planned_time",
            "passengers",
        ],
        order_by="idx asc",
    )
    # [#1f00x5]
    bldg_ids = {r["accommodation_building"] for r in rows if r.get("accommodation_building")}
    buildings = (
        {
            b["name"]: b
            for b in frappe.get_all(
                "Building",
                filters={"name": ["in", list(bldg_ids)]},
                fields=["name", "building_name", "city", "district", "google_maps_url"],
            )
        }
        if bldg_ids
        else {}
    )
    stops = []
    for r in rows:
        building = None
        if r.get("accommodation_building"):
            b = buildings.get(r["accommodation_building"])
            if b:
                building = {
                    "name": b.get("name"),
                    "building_name": b.get("building_name"),
                    "city": b.get("city"),
                    "district": b.get("district"),
                    "google_maps_url": b.get("google_maps_url"),
                }
        stops.append(
            {
                "stop_name": r.get("stop_name"),
                "sequence": r.get("idx"),
                "location": r.get("location"),
                "planned_time": _fmt_time(r.get("planned_time")),
                "expected_passengers": r.get("passengers"),
                "accommodation_building": r.get("accommodation_building"),
                "pickup": building,
            }
        )
    return stops


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
          "date": "2026-05-30",
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
        workers = _registered_workers(t.get("transport_request"))
        trips.append(
            {
                "dispatch_trip": t["name"],
                "transport_request": t.get("transport_request"),
                "route_plan": t.get("route_plan"),
                "vehicle": t.get("vehicle"),
                "depart_time": _fmt_time(t.get("depart_time")),
                "return_time": _fmt_time(t.get("return_time")),
                "status": t.get("status"),
                "expected_count": len(workers),
                "stops": _ordered_stops(t.get("route_plan")),
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
          "date": "2026-05-30",
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
        expected_total += len(_registered_workers(t.get("transport_request")))
        stops = _ordered_stops(t.get("route_plan"))
        stop_count += len(stops)
        if next_pickup is None:
            # [#jpju0q]
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


# [#74dyev]
# [#sfc8jm]
#   4. Mark each ignore_permissions write with an `# audit-ok` note stating the
# [#3n7rv4]

# [#r00mpe]
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

# [#dux84r]
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

# [#sncoz9]
WORKER_PREFERRED_LANGUAGES = ("English", "Arabic", "Urdu", "Hindi", "Bengali")

# [#1kncdr]
WORKER_PHOTO_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".heic", ".heif")
WORKER_PHOTO_MAX_BYTES = 8 * 1024 * 1024


# [#87hub4]
MASAR_TOKEN_COOKIE = TOKEN_COOKIES[WORKER]


def _token_from_request(token=None):
    """The personal token for this call: the explicit arg if given, else the
    httpOnly cookie. Returns '' when neither is present (resolver fails closed)."""
    return presented_token(WORKER, token)[0]


def _resolve_worker(token):
    """Resolve a required Worker credential to its exact active Employee.

    Every worker endpoint funnels through this fail-closed identity boundary; the
    client cannot widen its scope with an Employee id or another token audience.
    """
    return resolve_portal_subject(WORKER, token, required=True)


def _employee_doc(employee):
    """The Employee document, read defensively (fields vary across HR setups)."""
    return frappe.get_cached_doc("Employee", employee)


def _fmt_date(value):
    return frappe.utils.cstr(value) if value else None


# [#tultqv]
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
            # [#7r8jr6]
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
    emp = _employee_doc(employee)

    documents = []
    # [#nvwidj]
    iqama_no = emp.get("iqama") or emp.get("iqama_no")
    iqama_expiry = emp.get("iqama_expiry") or emp.get("valid_upto")
    if iqama_no or iqama_expiry:
        documents.append(
            {
                "type": "iqama",
                "number": iqama_no,
                "expiry": _fmt_date(iqama_expiry),
                "days_left": _days_until(iqama_expiry),
            }
        )
    # [#p42hfv]
    passport_no = emp.get("passport_number")
    passport_expiry = emp.get("passport_expiry")
    if passport_no:
        documents.append(
            {
                "type": "passport",
                "number": passport_no,
                "expiry": _fmt_date(passport_expiry),
                "days_left": _days_until(passport_expiry),
            }
        )

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
    }


def _active_assignment(employee):
    """The worker's current (submitted, not checked-out) Accommodation Assignment,
    or None. Scoped strictly to the resolved employee."""
    rows = frappe.get_all(
        "Housing Assignment",
        filters={
            "employee": employee,
            "docstatus": 1,
            "check_out_date": ["is", "not set"],
        },
        fields=[
            "name",
            "building",
            "room",
            "bed",
            "project",
            "check_in_date",
            "stay_type",
            "expected_checkout_date",
            "notes",
        ],
        order_by="check_in_date desc",
        limit=1,
    )
    return rows[0] if rows else None


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
            # [#le3pcb]
            _addr = get_address_text("Site", b.get("site")) or get_address_text(
                "Building", assignment["building"]
            )
            # [#s4cggu]
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


# [#77l2wp]
def _is_upcoming_pickup(pickup_datetime, now_dt=None):
    """True when ``pickup_datetime`` (a backend string or datetime) is at or after
    ``now_dt`` (defaults to now). A missing pickup is treated as upcoming so a
    not-yet-scheduled request never silently drops off the worker's view."""
    if not pickup_datetime:
        return True
    now_dt = now_dt or frappe.utils.now_datetime()
    try:
        return frappe.utils.get_datetime(pickup_datetime) >= now_dt
    except Exception:
        return True


# [#3pph3v]
def _worker_pickup_stop(stops, my_building):
    """The worker's OWN pickup stop from the ordered route stops.

    Prefers the housing pickup whose ``accommodation_building`` matches the
    worker's active Accommodation Assignment building; falls back to the first
    housing pickup (a stop carrying any ``accommodation_building``); finally to
    the first stop. Returns None only for an empty route."""
    if not stops:
        return None
    if my_building:
        for s in stops:
            if s.get("accommodation_building") == my_building:
                return s
    # [#5c8x93]
    for s in stops:
        if s.get("accommodation_building"):
            return s
    return stops[0]


def _route_destination_stop(stops, my_pickup):
    """The route's destination (final drop-off) stop.

    The drop-off is the last stop on the ordered route — the point AFTER every
    housing pickup. Returns None when the only stop is the worker's own pickup
    (a single-stop route has no separate destination to show)."""
    if not stops:
        return None
    last = stops[-1]
    if my_pickup is not None and last is my_pickup:
        return None
    return last


def _worker_transport_requests(employee):
    """Transport Requests whose worker manifest includes ``employee`` and that are
    still live (not Rejected/Cancelled/Fulfilled). Scoped via the child table."""
    parents = frappe.get_all(
        "Transport Request Worker",
        filters={"employee": employee, "parenttype": "Transport Request"},
        fields=["parent", "pickup_point"],
    )
    by_request = {}
    for p in parents:
        by_request.setdefault(p["parent"], p.get("pickup_point"))
    if not by_request:
        return []
    rows = frappe.get_all(
        "Transport Request",
        filters={
            "name": ["in", list(by_request.keys())],
            "service_line": ["in", list(WORKER_SERVICE_LINES)],
            "status": ["not in", ["Rejected", "Cancelled"]],
        },
        fields=[
            "name",
            "service_line",
            "request_type",
            "project",
            "accommodation_building",
            "pickup_datetime",
            "status",
            "route_plan",
            "assigned_vehicle",
            "assigned_driver",
            "dispatch_trip",
        ],
        order_by="pickup_datetime asc",
    )
    for r in rows:
        r["pickup_point"] = by_request.get(r["name"])
    return rows


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
    compatibility with any caller that read the old flat list."""
    employee = _resolve_worker(token)
    requests = _worker_transport_requests(employee)
    now_dt = frappe.utils.now_datetime()
    # [#dtcuvv]
    assignment = _active_assignment(employee)
    my_building = assignment.get("building") if assignment else None

    # [#hnuxj1]
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
            # [#phubnp]
            driver_map[d["name"]] = {"full_name": d["full_name"], "phone": d["phone"]}
    depart_map = {}
    if trip_names:
        for dt in frappe.get_all(
            "Dispatch Trip",
            filters={"name": ["in", list(trip_names)]},
            fields=["name", "depart_time"],
        ):
            depart_map[dt["name"]] = dt["depart_time"]
    rated_trips = set()
    if trip_names:
        rated_trips = set(
            frappe.get_all(
                "Transport Trip Rating",
                filters={"employee": employee, "dispatch_trip": ["in", list(trip_names)]},
                pluck="dispatch_trip",
            )
        )

    upcoming = []
    past = []
    for req in requests:
        vehicle = vehicle_map.get(req["assigned_vehicle"]) if req.get("assigned_vehicle") else None
        driver = driver_map.get(req["assigned_driver"]) if req.get("assigned_driver") else None
        depart_time = None
        if req.get("dispatch_trip"):
            depart_time = _fmt_time(depart_map.get(req["dispatch_trip"]))
        pickup_datetime = (
            frappe.utils.cstr(req["pickup_datetime"]) if req.get("pickup_datetime") else None
        )
        is_upcoming = _is_upcoming_pickup(req.get("pickup_datetime"), now_dt)
        stops = _ordered_stops(req.get("route_plan"))
        # [#73v959]
        my_pickup = _worker_pickup_stop(stops, my_building)
        destination = _route_destination_stop(stops, my_pickup)
        # [#4li4u0]
        has_rated = bool(
            req.get("dispatch_trip") and not is_upcoming and req["dispatch_trip"] in rated_trips
        )

        trip = {
            "transport_request": req["name"],
            # [#rf9139]
            "dispatch_trip": req.get("dispatch_trip") or _live_dispatch_trip(req["name"]),
            "request_type": req.get("request_type"),
            "status": req.get("status"),
            "pickup_point": req.get("pickup_point"),
            "pickup_datetime": pickup_datetime,
            "depart_time": depart_time,
            "is_upcoming": is_upcoming,
            "has_rated": bool(has_rated),
            "stops": stops,
            "my_pickup": my_pickup,
            "destination": destination,
            # [#fpyvhu]
            "maps_route_url": _full_route_maps_url(stops),
            "vehicle": vehicle,
            "driver": driver,
        }
        (upcoming if is_upcoming else past).append(trip)

    # [#g2nwgf]
    past.reverse()
    return {
        "date": frappe.utils.today(),
        "upcoming": upcoming,
        "past": past,
        "trips": upcoming,
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
            "creation",
        ],
        order_by="creation desc",
        limit=50,
    )
    for r in rows:
        r["creation"] = frappe.utils.cstr(r.get("creation"))
    return rows


# [#t322rd]
# [#afkogj]
_RESIDENT_REQUEST_SETTLED_STATES = ("Resolved", "Rejected", "Closed")


def _request_status_timeline(req):
    """A simple created -> current timeline for one resident request.

    The DocType has no explicit per-status history table, so we build the
    timeline from the available date fields: always a 'created' point (creation),
    and — when the request has reached a settled state — a 'closed' point
    (closed_on, falling back to modified). The current status is always carried
    as the active step so the UI can highlight where the request stands. Each
    point is ``{"key", "status", "timestamp"}`` with a bare string timestamp the
    client localizes; ordered oldest -> newest."""
    timeline = [
        {
            "key": "created",
            "status": "New",
            "timestamp": frappe.utils.cstr(req.get("creation")) if req.get("creation") else None,
        }
    ]
    status = req.get("status")
    if status in _RESIDENT_REQUEST_SETTLED_STATES:
        timeline.append(
            {
                "key": "closed",
                "status": status,
                "timestamp": frappe.utils.cstr(req.get("closed_on") or req.get("modified"))
                if (req.get("closed_on") or req.get("modified"))
                else None,
            }
        )
    else:
        # [#gdkpf5]
        if status and status != "New":
            timeline.append(
                {
                    "key": "current",
                    "status": status,
                    "timestamp": frappe.utils.cstr(req.get("modified"))
                    if req.get("modified")
                    else None,
                }
            )
    return timeline


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
    this endpoint cannot be used to read another worker's request.

    Returns the request's status, a reconstructed created -> current status
    timeline (the DocType has no status-history child table, so it is built from
    creation/modified/closed_on), the triage and resolution notes, the
    category/priority/location/description, and the attachment file url if any.
    Read-only, no commit, no GL."""
    employee = _resolve_worker(token)

    name = (name or "").strip()
    if not name:
        frappe.throw(_("A request reference is required."), frappe.PermissionError)

    # [#hua2eb]
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


def _custody_issued_by(custody_issue, building):
    """Name the supervisor who issued a held article to the worker.

    Custody Issue has no dedicated 'issued by' field, so the issuer is its
    ``owner`` (the user who created/submitted it), resolved to a person name.
    Falls back to the building's responsible facility supervisor, then None when
    nothing resolves (the client renders its own placeholder). Never throws —
    the worker view degrades gracefully."""
    owner = None
    if custody_issue:
        owner = frappe.db.get_value("Custody Issue", custody_issue, "owner")
    if owner:
        return frappe.utils.get_fullname(owner) or owner
    if building:
        sup = frappe.db.get_value(
            "Building", building, "responsible_supervisor"
        )
        if sup:
            return frappe.utils.get_fullname(sup) or sup
    return None


@frappe.whitelist(allow_guest=True)
@rate_limit(limit=60, seconds=60)
def get_worker_custody(token=None):
    """The custody articles the worker currently holds (read, token-scoped).

    Resolves the token to one Employee and returns their live custody holding,
    derived from the read-only Accommodation Stock Ledger — the same net-balance
    source as the ``Custody Outstanding by Worker`` report, not a Custody Issue
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
    from frappe.utils import flt

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

    agg = {}
    for r in rows:
        key = (r.building, r.item)
        bucket = agg.setdefault(
            key,
            {
                "item": r.item,
                "item_name": r.item_name,
                "building": r.building,
                "uom": r.uom,
                "qty": 0.0,
                "received_date": None,
                "_issue_voucher": None,
            },
        )
        bucket["qty"] += flt(r.signed_qty)
        # [#t7owl2]
        if flt(r.signed_qty) > 0:
            bucket["received_date"] = _fmt_date(r.posting_date)
            if r.voucher_type == "Custody Issue" and r.voucher_no:
                bucket["_issue_voucher"] = r.voucher_no

    items = []
    for bucket in agg.values():
        # [#lao4m9]
        if bucket["qty"] < 1e-9:
            continue
        bucket["issued_by"] = _custody_issued_by(bucket.pop("_issue_voucher"), bucket["building"])
        items.append(bucket)

    items.sort(key=lambda d: (d["item_name"] or d["item"] or "", d["building"] or ""))
    return {"items": items}


def _attach_worker_photo(doc, photo, photo_filename):
    """Attach a guest-supplied request photo to ``doc`` and set ``doc.attachment``.

    The image rides in as a base64 string (optionally a ``data:`` URI) on the same
    token-scoped POST that created the request — there is NO separate guest upload
    surface to harden. We validate the extension and decoded size ourselves, then
    persist a PRIVATE File attached to the just-created request via the framework's
    ``save_file`` (which re-checks the site max-file-size). The stored File path is
    written back to the request's ``attachment`` field so the existing detail view
    renders it. Returns silently on a blank/invalid photo — the field is optional,
    so a bad image must never sink an otherwise valid request."""
    from frappe.utils.file_manager import save_file

    photo = (photo or "").strip()
    if not photo:
        return

    fname = (photo_filename or "request-photo.jpg").strip() or "request-photo.jpg"
    # [#609lpl]
    fname = fname.replace("\\", "/").split("/")[-1]
    if not fname.lower().endswith(WORKER_PHOTO_EXTENSIONS):
        fname = f"{fname}.jpg"

    # [#artorm]
    payload = photo.split(",", 1)[1] if photo.startswith("data:") and "," in photo else photo
    if len(payload) * 3 / 4 > WORKER_PHOTO_MAX_BYTES:
        frappe.throw(_("The attached photo is too large."))

    saved = save_file(
        fname,
        photo,
        doc.doctype,
        doc.name,
        decode=True,
        is_private=1,
        df="attachment",
    )
    doc.db_set("attachment", saved.file_url)


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

    # [#mt3f8m]
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

    # [#djhanf]
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
    doc.insert(ignore_permissions=True)  # audit-ok — employee resolved from token server-side
    # [#aq6c4k]
    if photo:
        _attach_worker_photo(doc, photo, photo_filename)
    return {"name": doc.name, "status": doc.status}


# [#hometdy]
# [#keyejt]
_DOCUMENT_ALERT_LEAD_DAYS = 60

# [#348vlj]
_RESIDENT_REQUEST_CLOSED_STATES = ("Resolved", "Rejected", "Closed")


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
    # [#6lefv1]
    _resolve_worker(token)

    profile = get_worker_context(token)
    documents = profile.get("documents") or []
    profile_alerts = [
        d
        for d in documents
        if d.get("days_left") is not None and d["days_left"] <= _DOCUMENT_ALERT_LEAD_DAYS
    ]
    # [#hv1hes]
    iqama_days_left = next(
        (d.get("days_left") for d in documents if d.get("type") == "iqama"),
        None,
    )

    transport = get_worker_transport(token)
    # [#js5pkb]
    upcoming = transport.get("upcoming") or []
    next_ride = upcoming[0] if upcoming else None
    # [#dyj7k3]
    if next_ride:
        next_ride = {
            **next_ride,
            "eta_minutes": compute_ride_eta_minutes(
                next_ride.get("dispatch_trip"), _pickup_building_of(next_ride)
            ),
        }

    # [#e4b2n4]
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

    open_request_count = sum(
        1
        for r in list_worker_requests(token)
        if r.get("status") not in _RESIDENT_REQUEST_CLOSED_STATES
    )

    return {
        "date": frappe.utils.today(),
        "profile_alerts": profile_alerts,
        "next_ride": next_ride,
        "bed": bed,
        "open_request_count": open_request_count,
        "iqama_days_left": iqama_days_left,
    }


def _building_in_charge(employee):
    """The worker's current building in-charge contact, or None. Resolved from the
    active assignment's building (``responsible_supervisor`` User), the
    same source the accommodation screen uses."""
    assignment = _active_assignment(employee)
    user = assignment and frappe.db.get_value(
        "Building", assignment.get("building"), "responsible_supervisor"
    )
    if not user:
        return None
    return {
        "name": frappe.utils.get_fullname(user) or user,
        "phone": frappe.db.get_value("User", user, "mobile_no"),
    }


def _today_driver(employee):
    """The driver of the worker's today Dispatch Trip, or None. Resolved forward
    from today's trip on the worker's OWN manifest (via ``_worker_today_dispatch_trip``),
    so it can never reach a driver the worker is not riding with today."""
    resolved = _worker_today_dispatch_trip(employee)
    if not resolved:
        return None
    driver = frappe.db.get_value("Dispatch Trip", resolved[0], "driver")
    if not driver:
        return None
    d = frappe.db.get_value("Salis Driver", driver, ["full_name", "phone"], as_dict=True)
    return d or None


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


# [#l9ag3b]
_IQAMA_NOTIFY_HR_LEAD_DAYS = 30


def _hr_notify_recipients():
    """Enabled users to receive a worker's HR notification: HR Manager, falling
    back to System Manager. Mirrors temporary_worker_engine._hr_recipients so the
    Masar action lands in the same HR inbox the engine's automated alerts do."""
    from frappe.utils.user import get_users_with_role

    for role in ("HR Manager", "System Manager"):
        users = get_users_with_role(role)
        if users:
            return users
    return []


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=6, seconds=60 * 60)
def notify_hr_iqama_expiring(token=None):
    """One-tap: notify HR that the worker's Iqama is expiring (write, token-scoped).

    Resolves the token to one Employee via ``_resolve_worker`` (the only place
    identity is established — the client never supplies a worker id), re-reads
    that Employee's Iqama number + expiry SERVER-SIDE, and recomputes
    ``days_left``. The HR notification is raised ONLY when the Iqama is genuinely
    inside the action window (``days_left`` is known and <=
    ``_IQAMA_NOTIFY_HR_LEAD_DAYS``); a worker whose Iqama is comfortably valid, or
    has no expiry on file, is a silent no-op (``{"notified": False}``) — the
    client cannot force an alert by faking the threshold.

    When in window, posts a native in-app ``Notification Log`` (type Alert) to the
    HR inbox (HR Manager, fallback System Manager) — the SAME channel
    ``temporary_worker_engine._notify_hr`` uses; no separate ticketing engine, no
    GL. Tight ``rate_limit`` so the personal link cannot be used to spam HR.
    Returns ``{"notified": bool, "days_left": int|None, "recipients": int}``."""
    employee = _resolve_worker(token)
    emp = _employee_doc(employee)

    # [#ej5wro]
    iqama_no = emp.get("iqama") or emp.get("iqama_no")
    iqama_expiry = emp.get("iqama_expiry") or emp.get("valid_upto")
    days_left = _days_until(iqama_expiry)

    if days_left is None or days_left > _IQAMA_NOTIFY_HR_LEAD_DAYS:
        # [#h4f4zz]
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

    # Route through the shared system-notify helper: it adds the enabled-user check +
    # rollback/log_error that the raw loop lacked, so a DISABLED HR user is now skipped and
    # one failed insert no longer aborts the rest. Subject clip (140) + type Alert + Employee
    # link are identical to the old inline insert for an enabled recipient.
    recipients = _hr_notify_recipients()
    for user in recipients:
        notify_user_system(
            user,
            subject,
            message,
            document_type="Employee",
            document_name=employee,
        )

    return {"notified": True, "days_left": days_left, "recipients": len(recipients)}


# [#kmy4en]
_WORKER_BOARDING_METHOD = "Worker"


def _worker_today_dispatch_trip(employee, transport_request=None):
    """Resolve the ONE today's Dispatch Trip this worker may confirm boarding on.

    Resolved FORWARD from today's Dispatch Trips (Dispatch Trip -> Transport
    Request -> worker manifest), the same direction the driver QR scan and the
    driver route view resolve — NOT from the request's ``dispatch_trip``
    back-link, which is only stamped once a trip is Completed (a worker boards
    BEFORE completion). A trip qualifies only when its linked request carries
    THIS employee on its manifest, so the resolution can never reach a trip the
    worker is not on. A client-supplied ``transport_request`` only NARROWS that
    own-set; an id the worker is not registered on simply does not match. Returns
    ``(dispatch_trip, transport_request, stop_name, accommodation_building)`` or
    None when the worker has no boardable trip today."""
    # [#g58324]
    trips = frappe.get_all(
        "Dispatch Trip",
        filters={
            "trip_date": _trip_date_window(),
            "docstatus": ["<", 2],
            "status": ["not in", list(_FINISHED_TRIP_STATUSES)],
        },
        fields=["name", "route_plan", "transport_request"],
        order_by="depart_time asc",
    )
    if not trips:
        return None

    # [#ft5pfw]
    trip_names = [t["name"] for t in trips]

    # [#2pxml7]
    assigned_by_trip = {}
    for arow in frappe.get_all(
        "Dispatch Trip Assigned Request",
        filters={"parent": ["in", trip_names], "parenttype": "Dispatch Trip"},
        fields=["parent", "transport_request"],
        order_by="idx asc",
    ):
        assigned_by_trip.setdefault(arow["parent"], []).append(arow["transport_request"])

    # [#lilrjj]
    route_plan_names = [
        t["route_plan"] for t in trips if not t.get("transport_request") and t.get("route_plan")
    ]
    route_plan_req = {}
    if route_plan_names:
        for rp in frappe.get_all(
            "Route Plan",
            filters={"name": ["in", route_plan_names]},
            fields=["name", "transport_request"],
        ):
            route_plan_req[rp["name"]] = rp["transport_request"]

    # [#1rvc0x]
    worker_pickup = {}
    for wrow in frappe.get_all(
        "Transport Request Worker",
        filters={"parenttype": "Transport Request", "employee": employee},
        fields=["parent", "pickup_point"],
        order_by="modified asc",
    ):
        worker_pickup.setdefault(wrow["parent"], wrow.get("pickup_point"))

    for t in trips:
        req = t.get("transport_request")
        if not req and t.get("route_plan"):
            req = route_plan_req.get(t["route_plan"])
        # [#3x0xvi]
        candidate_reqs = [req, *assigned_by_trip.get(t["name"], [])]
        if transport_request:
            candidate_reqs = [r for r in candidate_reqs if r == transport_request]
        for candidate in candidate_reqs:
            if not candidate:
                continue
            # [#6cszu6]
            if candidate not in worker_pickup:
                continue
            building = frappe.db.get_value(
                "Transport Request", candidate, "accommodation_building"
            )
            return t["name"], candidate, worker_pickup[candidate], building
    return None


def _get_or_create_trip_log(dispatch_trip):
    """The trip's open (draft) Trip Start Log, created if none exists yet — the
    same get-or-create the driver QR scan uses (salis/api/boarding.py), so a
    worker self-confirm and a driver scan append to ONE shared log. A
    submitted/cancelled log is not reused; a fresh draft is opened so a
    post-submission confirm never mutates a closed record."""
    existing = frappe.db.get_value(
        "Trip Start Log", {"dispatch_trip": dispatch_trip, "docstatus": 0}, "name"
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
    log.insert(ignore_permissions=True)  # audit-ok — trip resolved from token's own manifest
    # [#18h8rg]
    from apex.salis.api.boarding_flow import ensure_trip_boarding_state

    ensure_trip_boarding_state(dispatch_trip)
    return log


def _already_boarded(log, employee):
    """True when this registered worker already has a boarding row on the log —
    so a re-confirm is idempotent (no duplicate headcount)."""
    return any(
        (row.worker == employee and not row.is_unregistered)
        for row in (log.boarding_events or [])
    )


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

    Strictly token-scoped: the boarding row is always written for the resolved
    employee, and the optional ``transport_request`` can only narrow the worker's
    own trip set (an id they are not registered on does not match). Re-confirming
    is idempotent — a worker already on the manifest yields no second row
    (``created = False``). A bad/blank/disabled token fails closed
    (PermissionError) before any write; a worker with no boardable trip today is a
    clean no-op (``{"trip": None}``). Posts no GL.

    Returns ``{"created": bool, "dispatch_trip": str|None, "trip_start_log":
    str|None, "boarded_count": int|None}``; ``{"trip": None}`` when nothing is
    boardable today."""
    employee = _resolve_worker(token)
    transport_request = (transport_request or "").strip() or None

    resolved = _worker_today_dispatch_trip(employee, transport_request)
    if not resolved:
        return {"trip": None, "created": False}
    dispatch_trip, request_name, stop_name, building = resolved

    # Serialize concurrent confirms for the same worker on the SAME Dispatch Trip row the
    # driver scan locks (salis/api/boarding.py): without it two simultaneous confirms both
    # read no open log / no boarding row and each writes one, double-boarding the worker.
    frappe.db.get_value("Dispatch Trip", dispatch_trip, "name", for_update=True)

    log = _get_or_create_trip_log(dispatch_trip)

    # [#f3nr8r]
    if _already_boarded(log, employee):
        return {
            "created": False,
            "dispatch_trip": dispatch_trip,
            "transport_request": request_name,
            "trip_start_log": log.name,
            "boarded_count": log.boarded_count,
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
    log.save(ignore_permissions=True)  # audit-ok — worker + trip resolved from token server-side
    # [#qoy1v1]
    from apex.salis.api.boarding_flow import mark_boarded

    mark_boarded(dispatch_trip, employee)
    return {
        "created": True,
        "dispatch_trip": dispatch_trip,
        "transport_request": request_name,
        "trip_start_log": log.name,
        "boarded_count": log.boarded_count,
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

    # [#ny5hpd]
    route_plan = frappe.db.get_value("Dispatch Trip", dispatch_trip, "route_plan") or frappe.db.get_value(
        "Transport Request", request_name, "route_plan"
    )
    stops = _ordered_stops(route_plan)
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


# [#q39fbh]
def _clean_adhoc_passengers(passengers):
    """Validate + normalize the client's ad-hoc passenger rows. Returns a list of
    clean dicts ready to append to the request's ``adhoc_passengers`` table; throws
    on a row missing a name or ID, or carrying an unparseable expiry."""
    import json

    if isinstance(passengers, str):
        passengers = json.loads(passengers or "[]")
    rows = []
    for p in passengers or []:
        full_name = (p.get("full_name") or "").strip()
        id_number = (p.get("id_number") or "").strip()
        if not full_name or not id_number:
            frappe.throw(_("Each additional passenger needs a name and an ID number."))
        expiry = (p.get("id_expiry") or "").strip() or None
        if expiry:
            try:
                expiry = frappe.utils.getdate(expiry).isoformat()
            except Exception:
                frappe.throw(_("An additional passenger's ID expiry is not a valid date."))
        rows.append(
            {
                "full_name": full_name[:140],
                "id_number": id_number[:64],
                "id_expiry": expiry,
                "nationality": (p.get("nationality") or "").strip()[:64] or None,
                "phone": (p.get("phone") or "").strip()[:32] or None,
            }
        )
    return rows


# [#6nk520]
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

    # [#fyh5gw]
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
    doc.insert(ignore_permissions=True)  # audit-ok — worker resolved from token server-side
    return {"name": doc.name, "status": doc.status, "adhoc_count": len(adhoc_rows)}


def _worker_was_on_trip(employee, dispatch_trip):
    """True when ``employee`` actually rode ``dispatch_trip``.

    ``Passenger Manifest`` has no ``employee`` column — the passengers live on its
    child ``Manifest Passenger`` — so the membership must be resolved through a
    child table, never a flat filter on the parent. Two authoritative links are
    honoured so a worker can rate a trip however it is tracked:

    1. Trip -> its Transport Request -> worker manifest (Transport Request Worker):
       the SAME demand->worker chain ``get_worker_transport`` scopes by; the trip
       carries its request from planning, long before the fulfilment back-link.
    2. Passenger Manifest for the trip lists the employee among its passengers
       (the on-board headcount record), matched via the child ``Manifest
       Passenger`` rows."""
    if not (employee and dispatch_trip):
        return False
    transport_request = frappe.db.get_value(
        "Dispatch Trip", dispatch_trip, "transport_request"
    )
    if transport_request and frappe.db.exists(
        "Transport Request Worker",
        {
            "parent": transport_request,
            "parenttype": "Transport Request",
            "employee": employee,
        },
    ):
        return True
    manifests = frappe.get_all(
        "Passenger Manifest", filters={"dispatch_trip": dispatch_trip}, pluck="name"
    )
    if manifests and frappe.db.exists(
        "Passenger Manifest Item",
        {
            "parent": ["in", manifests],
            "parenttype": "Passenger Manifest",
            "employee": employee,
        },
    ):
        return True
    return False


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=10, seconds=60)
def submit_trip_rating(token=None, dispatch_trip=None, rating=None, feedback=None, transport_request=None):
    """Allows a worker to submit a rating and feedback for a completed trip.

    Scoped by the worker's token to ensure they actually went on the trip.
    Creates a 'Transport Trip Rating' record."""
    employee = _resolve_worker(token)

    if not dispatch_trip:
        frappe.throw(_("Missing Dispatch Trip reference."))

    rating = frappe.utils.cint(rating)
    if rating < 1 or rating > 5:
        frappe.throw(_("Rating must be between 1 and 5."))

    # [#ilh5tr]
    if not _worker_was_on_trip(employee, dispatch_trip):
        frappe.throw(_("You were not part of this trip's manifest."), frappe.PermissionError)

    # [#tejynz]
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
        "rating": rating,
        "transport_request": transport_request,
        "feedback": (feedback or "").strip()[:2000]
    })
    doc.insert(ignore_permissions=True)
    return {"status": "success", "name": doc.name}
