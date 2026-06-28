# Copyright (c) 2026, AFMCO and contributors
"""Seed a small demo worker-movement scenario so Masar + the driver portal are
not empty for a first look.

A fresh site has no Dispatch Trips, Transport Requests, or Masar tokens, so both
the driver portal (My Trips and My Route) and the Masar worker app render empty
even for a correctly set-up user. This builds ONE complete, coherent, generic
worker-shuttle scenario in a SINGLE city (Riyadh):

  demo driver (User + Employee + Salis Driver)  ->  drives
  Dispatch Trip (today)  ->  Route Plan (housing-pickup stops linked to buildings
  carrying REAL Riyadh coordinates)  ->  Transport Request (Site Transport, worker
  manifest, future pickup so it reads as the worker's upcoming trip)
  with two demo worker Employees; the first is HOUSED (submitted Accommodation
  Assignment -> a real bed in building A) and carries a Masar Worker Token.

After it runs: the demo driver's portal shows a trip under My Trips and a worker
route under My Route; the demo worker's ``/masar?w=<token>`` shows an UPCOMING
trip (future pickup), their ACCOMMODATION (housed in building A), and contacts;
and the one-tap maps link chains the three buildings' real Riyadh coordinates in
order — no junk cross-city route.

Idempotent and install-safe: every record is get-or-created by a stable demo key,
so a re-run (or a second migrate) adds nothing; it is guarded behind the DocTypes
existing and wrapped so it can never fail an install/migrate. All names are
generic demo placeholders — no real personnel, contacts, or locations.
"""

import frappe

# Stable demo keys (idempotency anchors) — neutral placeholders, never real PII.
_DEMO_USER = "demo.driver@masar.example"
_DRIVER_NAME = "Demo Driver"
_WORKER_ONE = "Demo Worker One"
_WORKER_TWO = "Demo Worker Two"
_PROJECT = "Demo Transport Project"
_SITE = "Demo Housing Site"
_CITY = "Riyadh"
_ROUTE = "Demo Morning Shuttle"

# Three demo residences with DISTINCT real Riyadh coordinates, so the chained
# route has genuine in-city waypoints in order (lat,lng -> a Google Maps `q=` URL
# the maps-link builder reads back as exact coordinates). Building A is the one
# the demo worker is housed in.
_BUILDINGS = (
    {"name": "Demo Residence A", "lat": "24.7136", "lng": "46.6753", "district": "Al Olaya"},
    {"name": "Demo Residence B", "lat": "24.6877", "lng": "46.7219", "district": "Al Malaz"},
    {"name": "Demo Residence C", "lat": "24.7743", "lng": "46.7386", "district": "Al Murabba"},
)
_BUILDING = _BUILDINGS[0]["name"]  # the worker's home building


def _maps_url(lat, lng):
    """A clean Google Maps place URL carrying exact coordinates the waypoint
    builder reads back verbatim (``q=<lat>,<lng>``)."""
    return f"https://www.google.com/maps?q={lat},{lng}"


# Required DocTypes — if any is missing the scenario cannot be built; skip cleanly.
_REQUIRED = (
    "Salis Driver",
    "Transport Request",
    "Route Plan",
    "Dispatch Trip",
    "Masar Worker Token",
    "Accommodation Building",
    "Accommodation Room",
    "Accommodation Bed",
    "Accommodation Assignment",
)


def _company():
    return (
        frappe.defaults.get_global_default("company")
        or (frappe.get_all("Company", pluck="name", limit=1) or [None])[0]
    )


def _get_or_create(doctype, key_filters, make):
    name = frappe.db.get_value(doctype, key_filters, "name")
    if name:
        return name
    return make().name


def _project(company):
    return _get_or_create(
        "Project",
        {"project_name": _PROJECT},
        lambda: frappe.get_doc({"doctype": "Project", "project_name": _PROJECT}).insert(
            ignore_permissions=True  # audit-ok
        ),
    )


def _city():
    return _get_or_create(
        "City",
        {"city_name": _CITY},
        lambda: frappe.get_doc({"doctype": "City", "city_name": _CITY}).insert(
            ignore_permissions=True  # audit-ok
        ),
    )


def _site(company):
    city = _city()
    return _get_or_create(
        "Accommodation Site",
        {"site_name": _SITE},
        lambda: frappe.get_doc(
            {
                "doctype": "Accommodation Site",
                "site_name": _SITE,
                "company": company,
                "city": city,
            }
        ).insert(ignore_permissions=True),  # audit-ok
    )


def _building(spec, company, site):
    city = _city()
    return _get_or_create(
        "Accommodation Building",
        {"building_name": spec["name"]},
        lambda: frappe.get_doc(
            {
                "doctype": "Accommodation Building",
                "building_name": spec["name"],
                "site": site,
                "city": city,
                "district": spec["district"],
                "total_capacity": 40,
                "google_maps_url": _maps_url(spec["lat"], spec["lng"]),
            }
        ).insert(ignore_permissions=True),  # audit-ok
    )


def _room(building):
    """One ready demo room in ``building`` to hold the worker's bed."""
    room_number = f"{_BUILDING} R-101"
    return _get_or_create(
        "Accommodation Room",
        {"room_number": room_number},
        lambda: frappe.get_doc(
            {
                "doctype": "Accommodation Room",
                "building": building,
                "room_number": room_number,
                "floor": 1,
                "room_type": "Worker",
                "bed_capacity": 4,
                "status": "Available",
                "readiness_status": "Ready",
            }
        ).insert(ignore_permissions=True),  # audit-ok
    )


def _bed(room):
    bed_code = f"{_BUILDING} B-1"
    return _get_or_create(
        "Accommodation Bed",
        {"bed_code": bed_code},
        lambda: frappe.get_doc(
            {
                "doctype": "Accommodation Bed",
                "room": room,
                "bed_code": bed_code,
                "status": "Available",
            }
        ).insert(ignore_permissions=True),  # audit-ok
    )


def _assignment(employee, building, room, bed, project):
    """House the demo worker in building A (submitted, open stay) so the Masar
    accommodation card populates. Keyed on the worker's open assignment so a re-run
    never opens a second one."""
    existing = frappe.db.get_value(
        "Accommodation Assignment",
        {"employee": employee, "docstatus": 1, "check_out_date": ["is", "not set"]},
        "name",
    )
    if existing:
        return existing
    doc = frappe.get_doc(
        {
            "doctype": "Accommodation Assignment",
            "party_type": "Employee",
            "party": employee,
            "employee": employee,
            "building": building,
            "room": room,
            "bed": bed,
            "project": project,
            "assignment_type": "New Assignment",
            "stay_type": "Permanent",
            "check_in_date": frappe.utils.today(),
        }
    )
    doc.insert(ignore_permissions=True)  # audit-ok
    doc.submit()
    return doc.name


def _employee(first_name, company, user_id=None):
    filters = {"employee_name": first_name}
    name = frappe.db.get_value("Employee", filters, "name")
    if name:
        return name
    doc = {
        "doctype": "Employee",
        "first_name": first_name,
        "date_of_birth": "1990-01-01",
        "date_of_joining": frappe.utils.today(),
        "gender": "Male",
        "company": company,
        "status": "Active",
    }
    if user_id:
        doc["user_id"] = user_id
    return frappe.get_doc(doc).insert(ignore_permissions=True).name  # audit-ok


def _driver_user():
    if not frappe.db.exists("User", _DEMO_USER):
        frappe.get_doc(
            {
                "doctype": "User",
                "email": _DEMO_USER,
                "first_name": _DRIVER_NAME,
                "send_welcome_email": 0,
            }
        ).insert(ignore_permissions=True)  # audit-ok
    user = frappe.get_doc("User", _DEMO_USER)
    if "Driver" not in frappe.get_roles(_DEMO_USER):
        user.add_roles("Driver")
    return _DEMO_USER


def _driver(company):
    user = _driver_user()
    emp = _employee(_DRIVER_NAME, company, user_id=user)
    return _get_or_create(
        "Salis Driver",
        {"employee": emp},
        lambda: frappe.get_doc(
            {
                "doctype": "Salis Driver",
                "employee": emp,
                "full_name": _DRIVER_NAME,
                "status": "Active",
            }
        ).insert(ignore_permissions=True),  # audit-ok
    )


def _pickup_datetime():
    """Tomorrow 06:30 — a FUTURE pickup, so the worker's Masar Home and Transport
    both read this as the upcoming trip no matter what time of day the demo is
    opened (the upcoming/past split pivots on pickup vs now)."""
    return f"{frappe.utils.add_days(frappe.utils.today(), 1)} 06:30:00"


def _transport_request(company, project, building, driver, workers):
    name = frappe.db.get_value(
        "Transport Request", {"accommodation_building": building, "project": project}, "name"
    )
    if name:
        return name
    return (
        frappe.get_doc(
            {
                "doctype": "Transport Request",
                "service_line": "Site Transport",
                "request_type": "Accommodation to Project Shuttle",
                "project": project,
                "accommodation_building": building,
                "from_location": building,
                "to_location": "Project Site",
                "pickup_datetime": _pickup_datetime(),
                "assigned_driver": driver,
                "source_channel": "Desk",
                "status": "New",
                "workers": [{"employee": e, "pickup_point": "Building Gate"} for e in workers],
            }
        )
        .insert(ignore_permissions=True)  # audit-ok
        .name
    )


def _route_plan(project, driver, buildings, transport_request, workers):
    """The morning shuttle: a housing-pickup stop at each demo residence (each
    carrying real Riyadh coordinates) in order, then the project drop-off. The
    chained stops are what give the maps link real, in-order, in-city waypoints."""
    name = frappe.db.get_value("Route Plan", {"route_name": _ROUTE}, "name")
    if name:
        return name
    stops = []
    for i, b in enumerate(buildings, start=1):
        stops.append(
            {
                "sequence": i,
                "stop_name": f"Housing Pickup {i}",
                "accommodation_building": b,
                "location": "Building Gate",
                "passengers": len(workers) if i == 1 else 0,
            }
        )
    stops.append(
        {
            "sequence": len(buildings) + 1,
            "stop_name": "Project Drop-off",
            "location": "Project Site",
            "passengers": 0,
        }
    )
    return (
        frappe.get_doc(
            {
                "doctype": "Route Plan",
                "route_name": _ROUTE,
                "transport_request": transport_request,
                "project": project,
                "driver": driver,
                "stops": stops,
            }
        )
        .insert(ignore_permissions=True)  # audit-ok
        .name
    )


def _dispatch_trip(driver, route_plan, transport_request):
    # Keyed on the demo route plan so a re-run never opens a second trip. trip_date
    # is today so the driver portal (which shows today's trips) is not empty.
    name = frappe.db.get_value("Dispatch Trip", {"route_plan": route_plan}, "name")
    if name:
        return name
    return (
        frappe.get_doc(
            {
                "doctype": "Dispatch Trip",
                "route_plan": route_plan,
                "transport_request": transport_request,
                "driver": driver,
                "trip_date": frappe.utils.today(),
                "depart_time": "06:30:00",
                "status": "Planned",
            }
        )
        .insert(ignore_permissions=True)  # audit-ok
        .name
    )


def _link_transport_request(transport_request, route_plan, dispatch_trip):
    """Back-link the route plan + trip onto the request so the worker's Transport
    screen can resolve the ordered stops (it reads ``route_plan`` off the request)
    and a depart time. db_set so a re-run is a cheap idempotent no-op."""
    tr = frappe.get_doc("Transport Request", transport_request)
    if tr.route_plan != route_plan:
        tr.db_set("route_plan", route_plan)
    if tr.dispatch_trip != dispatch_trip:
        tr.db_set("dispatch_trip", dispatch_trip)


def _worker_token(employee):
    if frappe.db.get_value("Masar Worker Token", {"employee": employee}, "name"):
        return
    # autoname is field:party and naming runs before before_validate, so set the
    # Employee party pair up front (mirrors sync_party_employee) or naming throws
    # "Worker is required".
    frappe.get_doc(
        {
            "doctype": "Masar Worker Token",
            "party_type": "Employee",
            "party": employee,
            "employee": employee,
        }
    ).insert(ignore_permissions=True)  # audit-ok


def execute():
    try:
        # Demo data only on a developer/demo site — never seed a production site.
        if not frappe.conf.get("developer_mode"):
            return
        if any(not frappe.db.exists("DocType", dt) for dt in _REQUIRED):
            return
        company = _company()
        if not company:
            # No Company yet (very early install) — nothing to scope the demo to.
            return

        project = _project(company)
        site = _site(company)
        buildings = [_building(spec, company, site) for spec in _BUILDINGS]
        home_building = buildings[0]
        driver = _driver(company)
        w1 = _employee(_WORKER_ONE, company)
        w2 = _employee(_WORKER_TWO, company)
        workers = [w1, w2]

        # House the first demo worker in building A so /masar's accommodation card
        # populates. Isolated: a housing failure must not discard the trip/route.
        try:
            room = _room(home_building)
            bed = _bed(room)
            _assignment(w1, home_building, room, bed, project)
            frappe.db.commit()
        except Exception:
            frappe.db.rollback()
            frappe.log_error(
                title="seed_masar_demo_movement: accommodation",
                message=frappe.get_traceback(),
            )

        tr = _transport_request(company, project, home_building, driver, workers)
        rp = _route_plan(project, driver, buildings, tr, workers)
        dt = _dispatch_trip(driver, rp, tr)
        _link_transport_request(tr, rp, dt)
        frappe.db.commit()

        # The worker token is the Masar-app half; isolate it so a token failure does
        # not discard the trip/route the driver portal needs.
        try:
            _worker_token(w1)
            frappe.db.commit()
        except Exception:
            frappe.db.rollback()
            frappe.log_error(
                title="seed_masar_demo_movement: worker token",
                message=frappe.get_traceback(),
            )
    except Exception:
        frappe.db.rollback()
        frappe.log_error(
            title="seed_masar_demo_movement failed",
            message=frappe.get_traceback(),
        )
