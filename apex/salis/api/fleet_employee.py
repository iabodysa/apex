# Copyright (c) 2026, afmcoltd

import frappe
from frappe import _

from apex.apex_core.utils.portal_identity import DRIVER, as_capacity
from apex.salis.utils import (
    add_timeline_note,
    bound_vehicle,
    get_driver_for_session_user,
    period_quota,
)

_VEHICLE_STATUS_KEY = {
    "Active": "assigned",
    "Under Maintenance": "workshop",
    "Stopped": "stopped",
    "Released": "stopped",
}

_REGISTRATION_TYPE = "Registration (Istimara)"

def _session_driver(required=False):
    driver = get_driver_for_session_user(frappe.session.user)
    if required and not driver:
        frappe.throw(_("Your account is not linked to a fleet representative."), frappe.PermissionError)
    return driver

def _session_vehicle(driver):
    return bound_vehicle(driver) if driver else None

@frappe.whitelist()
def get_context():
    driver = _session_driver()
    if not driver:
        return {"state": "unlinked", "driver": None, "vehicle": None, "capabilities": {}}
    vehicle = _session_vehicle(driver)
    details = frappe.db.get_value(
        "Salis Driver", driver, ["full_name", "project", "status"], as_dict=True
    ) or {}
    plate = frappe.db.get_value("Salis Vehicle", vehicle, "plate_number") if vehicle else None
    assignment = frappe.db.get_value(
        "Vehicle Assignment",
        {"driver": driver, "vehicle": vehicle, "docstatus": 1, "status": "Active"},
        "name",
    ) if vehicle else None
    return {
        "state": "ready",
        "driver": driver,
        "driver_name": details.get("full_name"),
        "project": details.get("project"),
        "vehicle": vehicle,
        "vehicle_plate": plate,
        "assignment_status": "Active" if assignment else "Unassigned",
        "capabilities": {
            "handover": bool(vehicle and assignment),
            "fuel": bool(vehicle),
            "incident": bool(vehicle),
            "complaint": True,
        },
    }

def _registration_expiry(vehicle):
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
def get_fuel_stations():
    return frappe.get_list(
        "Fuel Platform",
        filters={"status": "Active"},
        pluck="name",
        order_by="platform_name asc",
        limit_page_length=0,
    )

@frappe.whitelist(methods=["POST"])
def submit_fuel_request(litres, vehicle=None, fuel_grade=None, station=None, notes=None):
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
    with as_capacity(DRIVER):
        doc.insert()

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
    driver = get_driver_for_session_user(frappe.session.user)
    if not driver:
        return []

    since = frappe.utils.add_days(frappe.utils.today(), -(frappe.utils.cint(days) or 90))
    rows = frappe.get_list(
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
            for v in frappe.get_list(
                "Salis Vehicle",
                filters={"name": ["in", list(vehicles)]},
                fields=["name", "plate_number"],
                limit_page_length=0,
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

from apex.salis.api.fleet_employee_services import (
    create_complaint,
    get_complaint,
    get_handover_checklist,
    get_my_complaints,
    get_my_fuel_quota,
    get_my_handovers,
    get_my_incidents,
    receive_vehicle,
    reply_to_complaint,
    report_incident,
    return_vehicle,
    submit_additional_fuel_request,
)

__all__ = [
    "create_complaint",
    "get_complaint",
    "get_handover_checklist",
    "get_my_complaints",
    "get_my_fuel_quota",
    "get_my_handovers",
    "get_my_incidents",
    "receive_vehicle",
    "reply_to_complaint",
    "report_incident",
    "return_vehicle",
    "submit_additional_fuel_request",
]
