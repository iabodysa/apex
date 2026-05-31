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

# Worker-transport requests are the Workers service line.
WORKER_SERVICE_LINE = "Workers"


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
        # The Dispatch Trip's transport_request is a read-only fetch from its
        # Route Plan; resolve it through the route plan if the fetch left it blank
        # so service-line filtering and the manifest lookup stay reliable.
        if not t.get("transport_request") and t.get("route_plan"):
            t["transport_request"] = frappe.db.get_value(
                "Route Plan", t["route_plan"], "transport_request"
            )
        service_line = None
        if t.get("transport_request"):
            service_line = frappe.db.get_value(
                "Transport Request", t["transport_request"], "service_line"
            )
        if service_line == WORKER_SERVICE_LINE:
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
            # Trips are already ordered by depart_time; the first housing-pickup
            # stop on the earliest trip is the driver's next pickup.
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


# ────────────────────────── Worker self-service (Masar app) ──────────────────────────
#
# These endpoints power the worker-facing Masar SPA (/masar). Workers are NOT
# Frappe users: identity comes from a personal, unguessable ``token`` (Masar
# Worker Token) that resolves server-side to exactly ONE Employee. The client
# NEVER supplies an employee id; every query below is scoped to the resolved
# employee, so a token can only ever surface its own worker's data — no
# cross-worker leakage. All endpoints are guest-accessible and read-mostly; the
# single writer (create_worker_request) reuses the native Accommodation Resident
# Request channel and posts no GL.

# Request categories the worker app exposes (a curated subset of the native
# Accommodation Resident Request "Category" options). VALUES stay English — they
# are sent straight to the DocType Select; the SPA translates only the labels.
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
    # Fail closed for an offboarded worker even if their token was never disabled:
    # a Left/Inactive employee's link must stop resolving.
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
    # Iqama / residence permit. Field names vary across HR setups (a custom
    # "iqama"/"iqama_no" + "iqama_expiry", or the standard HRMS "valid_upto" used
    # for the residence document). Read defensively; surface only when present.
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
    # Passport — standard HRMS fields passport_number + (custom) passport_expiry.
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
                "address",
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
            # City is autonamed by city_name, so the link value IS the city name.
            building = {
                "name": b.get("name"),
                "building_name": b.get("building_name"),
                "city": b.get("city"),
                "district": b.get("district"),
                "address": b.get("address"),
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
            "service_line": WORKER_SERVICE_LINE,
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
    """The worker's upcoming shuttle(s) (read, token-scoped).

    Resolves the token to one Employee and returns the transport requests that
    carry them — pickup point + time, the ordered route stops, and (when
    dispatched) the assigned vehicle/plate and driver name/contact. Scoped to the
    resolved employee via the Transport Request worker manifest; a worker on no
    live request gets ``{"trips": []}``. Read-only, no GL."""
    employee = _resolve_worker(token)
    requests = _worker_transport_requests(employee)
    trips = []
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
        trips.append(
            {
                "transport_request": req["name"],
                "request_type": req.get("request_type"),
                "status": req.get("status"),
                "pickup_point": req.get("pickup_point"),
                "pickup_datetime": frappe.utils.cstr(req["pickup_datetime"])
                if req.get("pickup_datetime")
                else None,
                "depart_time": depart_time,
                "stops": _ordered_stops(req.get("route_plan")),
                "vehicle": vehicle,
                "driver": driver,
            }
        )
    return {"date": frappe.utils.today(), "trips": trips}


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


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=10, seconds=60 * 60)
def create_worker_request(token=None, category=None, subject=None, body=None, priority=None):
    """Raise an Accommodation Resident Request for the worker (write, token-scoped).

    Reuses the native resident-request channel rather than inventing a ticketing
    engine. The employee, building, room and bed are taken from the worker's
    resolved identity + active assignment — NEVER from the client — so a request
    can only ever be filed for the token's own worker, against their own housing.
    Inserts a single ``source_channel = QR Web Form`` request as ``requester_type
    = Worker``; posts no GL. ``subject`` is folded into the description (the native
    DocType has no subject field)."""
    employee = _resolve_worker(token)

    category = (category or "Other").strip()
    if category not in WORKER_REQUEST_CATEGORIES:
        category = "Other"
    priority = (priority or "Low").strip()
    if priority not in ("Low", "Medium", "High", "Critical"):
        priority = "Low"

    subject = (subject or "").strip()
    body = (body or "").strip()
    if not body and not subject:
        frappe.throw(_("Please describe your request."))
    description = body if not subject else (f"{subject}\n\n{body}" if body else subject)

    # Housing context comes from the worker's OWN active assignment, server-side.
    assignment = _active_assignment(employee) or {}

    doc = frappe.get_doc(
        {
            "doctype": "Accommodation Resident Request",
            "source_channel": "QR Web Form",
            "requester_type": "Worker",
            "employee": employee,
            "worker_name": frappe.db.get_value("Employee", employee, "employee_name"),
            "building": assignment.get("building"),
            "room": assignment.get("room"),
            "bed": assignment.get("bed"),
            "request_category": category,
            "priority": priority,
            "description": description,
            "status": "New",
        }
    )
    doc.insert(ignore_permissions=True)  # audit-ok — employee resolved from token server-side
    return {"name": doc.name, "status": doc.status}
