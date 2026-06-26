"""Seed a small demo worker-movement scenario so Masar + the driver portal are
not empty for a first look.

A fresh site has no Dispatch Trips, Transport Requests, or Masar tokens, so both
the driver portal (My Trips and My Route) and the Masar worker app render empty
even for a correctly set-up user. This builds ONE complete, generic worker-shuttle
scenario for today:

  demo driver (User + Employee + Salis Driver)  ->  drives
  Dispatch Trip (today)  ->  Route Plan (housing-pickup stop linked to a building)
  ->  Transport Request (Site Transport, worker manifest)
  with two demo worker Employees, one carrying a Masar Worker Token.

After it runs: the demo driver's portal shows a trip under My Trips and a worker
route under My Route, and the demo worker's ``/masar?w=<token>`` link shows an
upcoming trip, accommodation, and contacts.

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
_BUILDING = "Demo Residence A"
_ROUTE = "Demo Morning Shuttle"

# Required DocTypes — if any is missing the scenario cannot be built; skip cleanly.
_REQUIRED = (
    "Salis Driver",
    "Transport Request",
    "Route Plan",
    "Dispatch Trip",
    "Masar Worker Token",
    "Accommodation Building",
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


def _site(company):
    return _get_or_create(
        "Accommodation Site",
        {"site_name": _SITE},
        lambda: frappe.get_doc(
            {"doctype": "Accommodation Site", "site_name": _SITE, "company": company}
        ).insert(ignore_permissions=True),  # audit-ok
    )


def _building(company):
    return _get_or_create(
        "Accommodation Building",
        {"building_name": _BUILDING},
        lambda: frappe.get_doc(
            {
                "doctype": "Accommodation Building",
                "building_name": _BUILDING,
                "site": _site(company),
                "total_capacity": 40,
                "google_maps_url": "https://maps.example/demo-residence-a",
            }
        ).insert(ignore_permissions=True),  # audit-ok
    )


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


def _transport_request(company, project, building, driver, workers):
    name = frappe.db.get_value(
        "Transport Request", {"accommodation_building": building, "project": project}, "name"
    )
    if name:
        return name
    # Pickup at today 06:30 + the driver assigned so the worker's Masar transport
    # card shows a real time and a callable driver contact, not a bare row.
    pickup = f"{frappe.utils.today()} 06:30:00"
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
                "pickup_datetime": pickup,
                "assigned_driver": driver,
                "source_channel": "Desk",
                "status": "New",
                "workers": [{"employee": e, "pickup_point": "Building Gate"} for e in workers],
            }
        )
        .insert(ignore_permissions=True)  # audit-ok
        .name
    )


def _route_plan(project, driver, building, transport_request, workers):
    name = frappe.db.get_value("Route Plan", {"route_name": _ROUTE}, "name")
    if name:
        return name
    return (
        frappe.get_doc(
            {
                "doctype": "Route Plan",
                "route_name": _ROUTE,
                "transport_request": transport_request,
                "project": project,
                "driver": driver,
                "stops": [
                    {
                        "sequence": 1,
                        "stop_name": "Housing Pickup",
                        "accommodation_building": building,
                        "location": "Building Gate",
                        "passengers": len(workers),
                    },
                    {
                        "sequence": 2,
                        "stop_name": "Project Drop-off",
                        "location": "Project Site",
                        "passengers": 0,
                    },
                ],
            }
        )
        .insert(ignore_permissions=True)  # audit-ok
        .name
    )


def _dispatch_trip(driver, route_plan, transport_request):
    # Keyed on the demo route plan so a re-run never opens a second trip.
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
        building = _building(company)
        driver = _driver(company)
        w1 = _employee(_WORKER_ONE, company)
        w2 = _employee(_WORKER_TWO, company)
        workers = [w1, w2]

        tr = _transport_request(company, project, building, driver, workers)
        rp = _route_plan(project, driver, building, tr, workers)
        _dispatch_trip(driver, rp, tr)
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
