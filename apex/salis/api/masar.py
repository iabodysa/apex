# Copyright (c) 2026, afmcoltd

import frappe
from frappe import _
from frappe.utils import cint

from apex.apex_core.utils.addresses import get_address_text
from apex.apex_core.utils.portal_identity import WORKER, as_capacity, portal_room
from apex.apex_core.utils.rate_limit_identity import rate_limit
from apex.apex_core.utils.role_assignment import role_holders_escalating
from apex.apex_core.utils.system_notify import notify_user_system
from apex.salis.api import boarding, boarding_window
from apex.salis.api.boarding import already_boarded
from apex.salis.api.boarding_flow import ensure_trip_boarding_state, mark_boarded
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

@frappe.whitelist(allow_guest=True)
@rate_limit(limit=60, seconds=60)
def get_worker_context(token=None):
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
    if not dispatch_trip:
        return None
    if dispatch_trip in status_map:
        return status_map[dispatch_trip]
    return frappe.db.get_value("Dispatch Trip", dispatch_trip, "status")

@frappe.whitelist(allow_guest=True)
@rate_limit(limit=60, seconds=60)
def get_worker_transport(token=None):
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
    vehicle_names = {r["assigned_vehicle"] for r in requests if r.get("assigned_vehicle")}
    driver_names = {r["assigned_driver"] for r in requests if r.get("assigned_driver")}
    trip_names = {r["dispatch_trip"] for r in requests if r.get("dispatch_trip")}

    vehicle_map = {}
    if vehicle_names:
        for v in frappe.get_all(
            "Salis Vehicle",
            filters={"name": ["in", list(vehicle_names)]},
            fields=["name", "vehicle_category"],
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
    field = frappe.get_meta("Transport Trip Rating").get_field("rating")
    return cint(field.options) or 5


def _alert_lead(fieldname: str, fallback: int) -> int:
    return cint(frappe.db.get_single_value("Salis Settings", fieldname)) or fallback


@frappe.whitelist(allow_guest=True)
@rate_limit(limit=60, seconds=60)
def get_worker_home(token=None):
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

def get_or_create_trip_log(dispatch_trip, employee=None):
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
    ensure_trip_boarding_state(dispatch_trip)
    return log

@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=12, seconds=60 * 60)
def confirm_boarding(token=None, transport_request=None):
    employee = _resolve_worker(token)
    transport_request = (transport_request or "").strip() or None

    resolved = _worker_today_dispatch_trip(employee, transport_request)
    if not resolved:
        return {"trip": None, "created": False}
    dispatch_trip, request_name, stop_name, building = resolved

    window = boarding_window.resolve(dispatch_trip, request_name, building)
    boarding_window.validate_window_is_open(window)

    frappe.db.get_value("Dispatch Trip", dispatch_trip, "name", for_update=True)

    log = get_or_create_trip_log(dispatch_trip, employee)

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

    board = []
    for t in trips:
        board.append(
            {
                "dispatch_trip": t["name"],
                "route_name": route_title.get(t.get("route_plan")) or t.get("route_plan"),
                "depart_time": _fmt_time(t.get("depart_time")),
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
