"""Masar (Worker Movement) driver-portal read APIs.

Masar is the **Workers division of Salis** — the worker-transport experience on
the shared fleet backbone. This module serves the worker-transport *trip view*
for the CURRENT driver: today's worker route, its ordered stops (the "trip road"),
and the per-stop manifest (registered workers + each stop's Habitat housing
pickup).

Every endpoint resolves the session user to a Salis Driver server-side (reusing
the driver-portal identity pattern); the client never supplies a driver id, and
nothing here writes — it is read-only and feeds the future Phase 1b worker-view
UI inside the existing /driver portal. No GL, no side-effects.
"""

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit

from apex_habitat.salis.api.driver_portal import _require_enabled, _resolve_driver

# [#6ddse8]
WORKER_SERVICE_LINES = ("Site Transport", "Inter-City Relocation")


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


def _today_worker_trips(driver):
    """Today's Dispatch Trips for ``driver`` whose linked Transport Request is on
    the Workers service line. Returns a list of trip dicts with the route_plan and
    transport_request resolved, ordered by departure time."""
    trips = frappe.get_all(
        "Dispatch Trip",
        filters={
            "driver": driver,
            "trip_date": frappe.utils.today(),
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
    worker_trips = []
    for t in trips:
        # [#pmk91w]
        if not t.get("transport_request") and t.get("route_plan"):
            t["transport_request"] = frappe.db.get_value(
                "Route Plan", t["route_plan"], "transport_request"
            )
        service_line = None
        if t.get("transport_request"):
            service_line = frappe.db.get_value(
                "Transport Request", t["transport_request"], "service_line"
            )
        if service_line in WORKER_SERVICE_LINES:
            worker_trips.append(t)
    return worker_trips


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
    workers = []
    for r in rows:
        workers.append(
            {
                "employee": r.get("employee"),
                "employee_name": (
                    frappe.db.get_value("Employee", r["employee"], "employee_name")
                    if r.get("employee")
                    else None
                ),
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
            "sequence",
            "stop_name",
            "accommodation_building",
            "location",
            "planned_time",
            "passengers",
        ],
        order_by="sequence asc, idx asc",
    )
    stops = []
    for r in rows:
        building = None
        if r.get("accommodation_building"):
            b = frappe.db.get_value(
                "Accommodation Building",
                r["accommodation_building"],
                ["name", "building_name", "city", "district", "google_maps_url"],
                as_dict=True,
            )
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
                "sequence": r.get("sequence"),
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

    Resolves the session user to a Salis Driver server-side (no client-supplied
    id) and returns today's Workers-line route(s): for each trip, the route plan,
    its ordered stops (each with its Habitat housing pickup when linked), and the
    registered worker manifest carried by the linked Transport Request.

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

    Resolves the session user to a Salis Driver server-side (no client-supplied
    id) and folds today's Workers-line trips into headline counts plus a single
    "next pickup" pointer (the earliest housing-pickup stop on the earliest trip).
    Read-only; writes nothing and posts no GL.

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

# [#t306loc] Issue Location Select options — mirror the Accommodation Resident
# Request DocType field exactly; a client value outside this set is dropped (the
# field is optional, so no throw — it simply isn't set).
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

# [#t306lang] Preferred Language Select options — mirror the DocType field. The
# worker portal offers only the two it is localized in (English/Arabic); the
# wider set is accepted here so the field stays in sync if the UI grows.
WORKER_PREFERRED_LANGUAGES = ("English", "Arabic", "Urdu", "Hindi", "Bengali")

# [#t306photo] Guest-uploadable request photo: only real image types, capped so a
# guest POST can never push an oversized blob through the create endpoint.
WORKER_PHOTO_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".heic", ".heif")
WORKER_PHOTO_MAX_BYTES = 8 * 1024 * 1024


def _resolve_worker(token):
    """Resolve a personal Masar token to its single Employee, or 403.

    This is the ONE place a worker identity is established. Every worker endpoint
    funnels through here, so data access is bound to the token's employee and can
    never be widened by a client-supplied id. An unknown, blank, or disabled
    token is rejected with a PermissionError (not a soft empty) so a bad link
    fails closed."""
    token = (token or "").strip()
    if not token:
        frappe.throw(_("A worker link token is required."), frappe.PermissionError)
    row = frappe.db.get_value(
        "Masar Worker Token",
        {"token": token, "enabled": 1},
        ["employee", "employee_name"],
        as_dict=True,
    )
    if not row or not row.get("employee"):
        frappe.throw(_("This worker link is invalid or has been disabled."), frappe.PermissionError)
    # [#58u5n5]
    if frappe.db.get_value("Employee", row["employee"], "status") in ("Inactive", "Left"):
        frappe.throw(_("This worker link is invalid or has been disabled."), frappe.PermissionError)
    return row["employee"]


def _employee_doc(employee):
    """The Employee document, read defensively (fields vary across HR setups)."""
    return frappe.get_cached_doc("Employee", employee)


def _fmt_date(value):
    return frappe.utils.cstr(value) if value else None


def _days_until(value):
    """Whole days from today until ``value`` (a date), or None."""
    if not value:
        return None
    try:
        return frappe.utils.date_diff(value, frappe.utils.today())
    except Exception:
        return None


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
        "Accommodation Assignment",
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
    from apex_habitat.apex_core.utils.addresses import get_address_text

    employee = _resolve_worker(token)
    assignment = _active_assignment(employee)
    if not assignment:
        return {"assignment": None}

    building = None
    if assignment.get("building"):
        b = frappe.db.get_value(
            "Accommodation Building",
            assignment["building"],
            [
                "name",
                "building_name",
                "city",
                "district",
                "site",
                "google_maps_url",
                "responsible_facility_supervisor",
                "current_occupants",
                "total_capacity",
            ],
            as_dict=True,
        )
        if b:
            in_charge = None
            user = b.get("responsible_facility_supervisor")
            if user:
                in_charge = {
                    "name": frappe.utils.get_fullname(user) or user,
                    "phone": frappe.db.get_value("User", user, "mobile_no"),
                }
            # [#le3pcb]
            _addr = get_address_text("Accommodation Site", b.get("site")) or get_address_text(
                "Accommodation Building", assignment["building"]
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
            "Accommodation Room",
            assignment["room"],
            ["name", "room_number", "floor", "room_type", "bed_capacity", "current_occupancy"],
            as_dict=True,
        )
        room = r or None

    bed = None
    if assignment.get("bed"):
        bd = frappe.db.get_value(
            "Accommodation Bed", assignment["bed"], ["name", "bed_code", "status"], as_dict=True
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


# [T-537] A trip is "upcoming" when its pickup is at or after this instant;
# anything earlier is "past". Home's next_ride and Transport's upcoming list both
# pivot on this one predicate so the two screens can never contradict each other.
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

    [T-537] Each trip is tagged ``is_upcoming`` against ``now_datetime()`` (the
    SAME predicate Home's next_ride uses), and the trips are partitioned into
    ``upcoming`` and ``past`` so the Transport screen can never present a trip
    that already departed as if it were the next ride — Home and Transport stay
    in lock-step. ``trips`` is kept as an alias of ``upcoming`` for backward
    compatibility with any caller that read the old flat list."""
    employee = _resolve_worker(token)
    requests = _worker_transport_requests(employee)
    now_dt = frappe.utils.now_datetime()
    upcoming = []
    past = []
    for req in requests:
        vehicle = None
        if req.get("assigned_vehicle"):
            v = frappe.db.get_value(
                "Salis Vehicle",
                req["assigned_vehicle"],
                ["name", "plate_number", "vehicle_category"],
                as_dict=True,
            )
            vehicle = v or None
        driver = None
        if req.get("assigned_driver"):
            d = frappe.db.get_value(
                "Salis Driver", req["assigned_driver"], ["full_name", "phone"], as_dict=True
            )
            driver = d or None
        depart_time = None
        if req.get("dispatch_trip"):
            depart_time = _fmt_time(
                frappe.db.get_value("Dispatch Trip", req["dispatch_trip"], "depart_time")
            )
        pickup_datetime = (
            frappe.utils.cstr(req["pickup_datetime"]) if req.get("pickup_datetime") else None
        )
        is_upcoming = _is_upcoming_pickup(req.get("pickup_datetime"), now_dt)
        trip = {
            "transport_request": req["name"],
            "request_type": req.get("request_type"),
            "status": req.get("status"),
            "pickup_point": req.get("pickup_point"),
            "pickup_datetime": pickup_datetime,
            "depart_time": depart_time,
            "is_upcoming": is_upcoming,
            "stops": _ordered_stops(req.get("route_plan")),
            "vehicle": vehicle,
            "driver": driver,
        }
        (upcoming if is_upcoming else past).append(trip)

    # Past trips read newest-first (most recently departed at the top); upcoming
    # stays soonest-first as the underlying query already ordered them.
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
        "Accommodation Resident Request",
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
# Accommodation Resident Request has NO status-history child table, so the
# detail timeline is reconstructed from the few durable timestamps the DocType
# carries: creation (raised), modified (last update), and closed_on (settled).
# Status states that are settled -> their closed point is closed_on||modified.
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
        # Live request: surface the current state at its last-updated time so the
        # timeline shows movement (New -> current) without inventing per-status dates.
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

    # [#t322own] Ownership gate: key the fetch on name AND employee=<resolved>,
    # mirroring list_worker_requests' filter exactly. A request owned by another
    # worker does not match -> no row -> PermissionError. The client name alone
    # can never widen access beyond the token's own employee.
    req = frappe.db.get_value(
        "Accommodation Resident Request",
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
            "Accommodation Building", building, "responsible_facility_supervisor"
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
            "qty",
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
        bucket["qty"] += flt(r.qty)
        # [#cstdy1] latest issue (positive) row drives the worker-facing
        # "received date" + the source Custody Issue used to name the supervisor
        if flt(r.qty) > 0:
            bucket["received_date"] = _fmt_date(r.posting_date)
            if r.voucher_type == "Custody Issue" and r.voucher_no:
                bucket["_issue_voucher"] = r.voucher_no

    items = []
    for bucket in agg.values():
        # [#cstdy2] only still-held positive net holdings; drop returned/zero rows
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
    # Keep only the base name + a known image extension; default unknown to .jpg.
    fname = fname.replace("\\", "/").split("/")[-1]
    if not fname.lower().endswith(WORKER_PHOTO_EXTENSIONS):
        fname = f"{fname}.jpg"

    # Rough decoded-size guard BEFORE decode (base64 is ~4/3 of the bytes); the
    # framework's check_max_file_size re-checks the exact size inside save_file.
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

    # [#t306loc] / [#t306lang] optional, drop anything outside the Select set
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
            "doctype": "Accommodation Resident Request",
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
    # [#t306photo] attach after insert so the File can bind to the saved name
    if photo:
        _attach_worker_photo(doc, photo, photo_filename)
    return {"name": doc.name, "status": doc.status}


# [#hometdy]
# Document is "expiring soon" within this many days — mirrors the established
# Habitat renewal lead (Building License default renewal_lead_days = 60). A
# negative days_left (already past) always alerts.
_DOCUMENT_ALERT_LEAD_DAYS = 60

# Accommodation Resident Request states that are settled, so NOT counted as open.
# (Status options: New / Triaged / Assigned / In Progress / Waiting Evidence /
# Resolved / Rejected / Closed — see the DocType.)
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

    Purely additive: it composes the existing token-scoped endpoints (each
    re-resolves the same token via ``_resolve_worker``) and changes none of
    them. Read-only, no commit, no GL."""
    # [#hometdy] resolve once up front so a bad/disabled token fails closed here
    # exactly as the sibling endpoints do (each re-resolves it too).
    _resolve_worker(token)

    profile = get_worker_context(token)
    profile_alerts = [
        d
        for d in (profile.get("documents") or [])
        if d.get("days_left") is not None and d["days_left"] <= _DOCUMENT_ALERT_LEAD_DAYS
    ]

    transport = get_worker_transport(token)
    # [T-536] / [T-537] the "next" ride is the soonest UPCOMING trip, never an
    # already-departed one. get_worker_transport now partitions on the SAME
    # now_datetime() predicate, so Home's next_ride is literally the head of the
    # list Transport shows under "upcoming" — the two screens cannot disagree.
    upcoming = transport.get("upcoming") or []
    next_ride = upcoming[0] if upcoming else None

    # [T-538] the bed is shown on Home as a glanceable chip, but a bare bed code
    # ("DEMO-R-103-B2") tells the worker nothing. Carry the building + room (and
    # check-in) the accommodation endpoint already resolved so the chip reads as a
    # real location. building/room may be None (degrade cleanly on the client).
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
    }


# [T-324] The worker may one-tap "notify HR" only once their Iqama is inside this
# window. Distinct from the 60-day _DOCUMENT_ALERT_LEAD_DAYS visual alert: the
# action is the tighter, action-worthy threshold the task fixes at 30 days. The
# server re-checks it from the Employee record, so a client can never trigger the
# alert outside this window.
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

    # [#nvwidj] same defensive field reads get_worker_context uses — Iqama field
    # names vary by HR setup; recompute days_left from the record, never the client.
    iqama_no = emp.get("iqama") or emp.get("iqama_no")
    iqama_expiry = emp.get("iqama_expiry") or emp.get("valid_upto")
    days_left = _days_until(iqama_expiry)

    if days_left is None or days_left > _IQAMA_NOTIFY_HR_LEAD_DAYS:
        # Out of window (or no expiry on file): refuse silently, raise nothing.
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

    recipients = _hr_notify_recipients()
    for user in recipients:
        frappe.get_doc(
            {
                "doctype": "Notification Log",
                "for_user": user,
                "type": "Alert",
                "document_type": "Employee",
                "document_name": employee,
                "subject": subject[:140],
                "email_content": message,
            }
        ).insert(ignore_permissions=True)  # audit-ok — worker resolved from token server-side

    return {"notified": True, "days_left": days_left, "recipients": len(recipients)}
