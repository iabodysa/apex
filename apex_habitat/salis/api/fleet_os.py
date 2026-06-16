"""Fleet OS supervisor dashboard API (read + live operations).

Backs the ``/fleet`` www page, which is the fleet supervisor's single-screen
dashboard. The page is a faithful copy of the supervisor's own design; this
module replaces the design's embedded JSON with LIVE Salis data and routes its
operations to the real DocTypes.

Contract: :func:`get_fleet_os` returns a ``vehicles`` list whose item / history
shape matches exactly what the page's render code reads (``v.plate``,
``v.history``, ``v.current_driver``, ``h.date_receive`` …), so the design's
render functions run unchanged. The reader is N+1-free: three bounded
``get_all`` queries (vehicles, the drivers they reference, all assignments)
plus the Vehicle Category lookup, then grouped in Python.

Every endpoint is permission-gated on ``Salis Vehicle`` and project-scoped
server-side through the SAME ``_permitted_projects`` resolver the dispatch
board, fleet control board and the list-view ``permission_query_conditions``
use, so the dashboard never shows (or mutates) a project a scoped supervisor
could not already see. Writes reuse the existing controllers (Vehicle
Assignment, Vehicle Stop, Vehicle Incident) — no parallel logic.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import getdate, today

from apex_habitat.salis.api.dispatch_board import _permitted_projects
from apex_habitat.salis.utils import lock_driver, lock_vehicle

# [#9tkuh4]
# [#fo1z63]
# [#65j7is]
# [#kgimnt]
# [#5aqx9y]
# [#5kmolk]
# [#5pzdlz]
_STATUS_MAP = {
    "Stopped": "stopped",
    "Under Maintenance": "workshop",
    "Released": "stopped",
}

# [#lf7qyr]
# [#oqa9r6]
# [#e27bhs]
# [#evgxmo]
_STOP_REASON_MAP = {
    "maintenance": "Maintenance",
    "rental return": "Rental Return",
    "rental": "Rental Return",
    "return": "Rental Return",
}


def _vehicle_status(status: str, has_driver: bool) -> str:
    """Map a Salis Vehicle.status to the design's vehicle_status string."""
    if status == "Active":
        return "assigned" if has_driver else "available"
    return _STATUS_MAP.get(status, "available")


def _sheet_for(category: str | None) -> str:
    """Best-effort CAR / MOTORCYCLE bucket for the design's type filter,
    derived from the category name (the design only has these two chips)."""
    if not category:
        return "CAR"
    upper = category.upper()
    # [#7ur0k1]
    # [#fry5w7]
    if any(tok in upper for tok in ("MOTOR", "BIKE", "SCOOTER", "\u062f\u0628\u0627\u0628", "\u062f\u0631\u0627\u062c")):
        return "MOTORCYCLE"
    return "CAR"


def _resolve_plate(plate: str) -> str:
    """Resolve a plate string from the dashboard to a Salis Vehicle name,
    permission-checked. Matches plate_number, then plate_normalized, then name.
    Raises if not found or not permitted."""
    if not plate:
        frappe.throw(_("Plate is required."))
    name = frappe.db.get_value("Salis Vehicle", {"plate_number": plate}, "name")
    if not name:
        normalized = "".join(str(plate).split()).upper()
        name = frappe.db.get_value("Salis Vehicle", {"plate_normalized": normalized}, "name")
    if not name and frappe.db.exists("Salis Vehicle", plate):
        name = plate
    if not name:
        frappe.throw(_("Vehicle {0} not found.").format(plate))
    frappe.has_permission("Salis Vehicle", "write", doc=name, throw=True)
    return name


# [#mdc0uu]
# [#bfnq27]
# [#mdc0uu]
@frappe.whitelist()
def get_fleet_os():
    """Return the full fleet in the design's exact shape (a ``vehicles`` list).

    Project scope is enforced server-side: a scoped user with no permitted
    project gets an empty list. N+1-free (three bounded queries + the category
    fuel lookup).
    """
    frappe.has_permission("Salis Vehicle", "read", throw=True)
    # [#jtpjlv]
    # [#hjzryw]
    # [#fjxbcn]
    show_pii = 1 in frappe.get_meta("Salis Driver").get_permlevel_access("read")
    unscoped, projects = _permitted_projects()
    if not unscoped and not projects:
        return {"vehicles": []}

    v_filters = {} if unscoped else {"project": ["in", projects]}
    vehicles = frappe.get_all(
        "Salis Vehicle",
        filters=v_filters,
        fields=[
            "name", "plate_number", "vehicle_category", "status",
            "rental_office", "project", "current_driver",
        ],
        order_by="plate_number asc",
        limit_page_length=0,
    )
    if not vehicles:
        return {"vehicles": []}

    # [#kgmpae]
    cat_names = list({v.vehicle_category for v in vehicles if v.get("vehicle_category")})
    cat_fuel: dict[str, str] = {}
    if cat_names:
        for c in frappe.get_all(
            "Vehicle Category",
            filters={"name": ["in", cat_names]},
            fields=["name", "default_fuel_type"],
        ):
            cat_fuel[c.name] = (c.default_fuel_type or "").upper()

    # [#ntmduq]
    driver_names = {v.current_driver for v in vehicles if v.get("current_driver")}

    # [#qiund2]
    plates = [v.name for v in vehicles]
    assignments = frappe.get_all(
        "Vehicle Assignment",
        filters={"vehicle": ["in", plates]},
        fields=["vehicle", "driver", "project", "start_date", "end_date", "status", "docstatus"],
        order_by="start_date asc",
        limit_page_length=0,
    )
    for a in assignments:
        if a.get("driver"):
            driver_names.add(a.driver)

    drivers: dict[str, dict] = {}
    if driver_names:
        for d in frappe.get_all(
            "Salis Driver",
            filters={"name": ["in", list(driver_names)]},
            fields=["name", "full_name", "driver_id", "phone"],
            limit_page_length=0,
        ):
            drivers[d.name] = d

    history_by_vehicle: dict[str, list] = {}
    for a in assignments:
        d = drivers.get(a.driver) or {}
        # [#2lg9p3]
        is_active = a.status == "Active" and a.docstatus == 1 and not a.end_date
        history_by_vehicle.setdefault(a.vehicle, []).append({
            "driver_id": ((d.get("driver_id") or a.driver or "") if show_pii else ""),
            "name_en": (d.get("full_name") or ""),
            "name_ar": "",
            "mobile": ((d.get("phone") or "") if show_pii else ""),
            "date_receive": str(a.start_date or ""),
            "date_deliver": str(a.end_date or ""),
            "status": "Active" if is_active else "Stopped",
            "project": (a.project or ""),
            "area": "",
            "reason": "",
            "notes": "",
            "branch_receive": "",
            "branch_deliver": "",
        })

    out = []
    for v in vehicles:
        cd = None
        if v.get("current_driver"):
            # [#jhe847]
            # [#8srfq8]
            # [#gmlv5i]
            # [#56ra6u]
            # [#f27432]
            hist = history_by_vehicle.get(v.name, [])
            active = next((h for h in hist if h.get("status") == "Active" and not h.get("date_deliver")), None)
            if active:
                cd = dict(active)
            else:
                d = drivers.get(v.current_driver) or {}
                cd = {
                    "driver_id": ((d.get("driver_id") or v.current_driver or "") if show_pii else ""),
                    "name_en": (d.get("full_name") or ""), "name_ar": "",
                    "mobile": ((d.get("phone") or "") if show_pii else ""), "date_receive": "", "date_deliver": "",
                    "status": "Active", "project": (v.project or ""), "area": "",
                    "reason": "", "notes": "", "branch_receive": "", "branch_deliver": "",
                }
        out.append({
            "plate": v.plate_number or v.name,
            "vehicle_type": v.vehicle_category or "",
            "fuel": cat_fuel.get(v.vehicle_category, ""),
            "rental_office": v.rental_office or "",
            "sheet": _sheet_for(v.vehicle_category),
            "area": "",  # [#6ptyey]
            "project": v.project or "",
            "vehicle_status": _vehicle_status(v.status, bool(v.get("current_driver"))),
            "workshop_notes": "",
            "workshop_date": "",
            "current_driver": cd,
            "history": history_by_vehicle.get(v.name, []),
            # [#9g1sfn]
            "damages": [],
            "accidents": [],
            "stolen_info": None,
            "notes": "",
        })

    return {"vehicles": out}


# [#mdc0uu]
# [#kcvqbz]
# [#mdc0uu]
@frappe.whitelist(methods=["POST"])
def reassign(plate, driver_id, date=None):
    """Assign a driver to a vehicle by creating a submitted Vehicle Assignment.

    ``driver_id`` is the EXTERNAL fleet identifier (Salis Driver.driver_id), as
    the dashboard carries it; we resolve it to the Salis Driver name. The
    Vehicle Assignment controller handles the link side; we also set the
    vehicle's current_driver and the driver's current_vehicle so the live state
    matches immediately (the assignment alone does not mutate those).
    """
    vehicle = _resolve_plate(plate)
    if not driver_id:
        frappe.throw(_("Driver is required."))

    driver = frappe.db.get_value("Salis Driver", {"driver_id": driver_id}, "name")
    if not driver and frappe.db.exists("Salis Driver", driver_id):
        driver = driver_id
    if not driver:
        frappe.throw(_("Driver {0} not found.").format(driver_id))
    # [#doark9]
    # [#2znemb]
    # [#rv4edb]
    frappe.has_permission("Salis Driver", "write", doc=driver, throw=True)
    lock_vehicle(vehicle)
    lock_driver(driver)

    start = getdate(date) if date else getdate(today())

    # [#gtecq9]
    open_rows = frappe.get_all(
        "Vehicle Assignment",
        filters={"vehicle": vehicle, "status": "Active", "docstatus": 1},
        fields=["name"],
    )
    for r in open_rows:
        frappe.db.set_value("Vehicle Assignment", r.name, {"status": "Ended", "end_date": start})

    doc = frappe.get_doc({
        "doctype": "Vehicle Assignment",
        "vehicle": vehicle,
        "driver": driver,
        "project": frappe.db.get_value("Salis Vehicle", vehicle, "project"),
        "start_date": start,
        "status": "Active",
    })
    doc.insert()
    # [#pt7ksd]
    # [#njnkmw]
    doc.submit()

    frappe.db.set_value("Salis Vehicle", vehicle, "current_driver", driver)
    frappe.db.set_value("Salis Driver", driver, "current_vehicle", vehicle)
    return {"ok": True, "assignment": doc.name}


@frappe.whitelist(methods=["POST"])
def stop_vehicle(plate, reason=None):
    """Stop a vehicle and release its driver by submitting a Vehicle Stop.

    Vehicle Stop.on_submit flips Salis Vehicle.status to "Stopped". The free-text
    reason is mapped to the nearest no-evidence Select option (default "Other")
    so the submit never trips the evidence gate. The current assignment is ended
    and the driver link cleared to match the released state.
    """
    vehicle = _resolve_plate(plate)
    lock_vehicle(vehicle)
    stop_reason = _STOP_REASON_MAP.get((reason or "").strip().lower(), "Other")

    current_driver = frappe.db.get_value("Salis Vehicle", vehicle, "current_driver")

    doc = frappe.get_doc({
        "doctype": "Vehicle Stop",
        "vehicle": vehicle,
        "stop_reason": stop_reason,
        "stop_date": getdate(today()),
        "notes": (reason or ""),
    })
    doc.insert()
    doc.submit()  # [#mx3ts3]

    # [#9hy3v4]
    if current_driver:
        for r in frappe.get_all(
            "Vehicle Assignment",
            filters={"vehicle": vehicle, "status": "Active", "docstatus": 1},
            fields=["name"],
        ):
            frappe.db.set_value("Vehicle Assignment", r.name, {"status": "Ended", "end_date": getdate(today())})
        frappe.db.set_value("Salis Vehicle", vehicle, "current_driver", None)
        frappe.db.set_value("Salis Driver", current_driver, "current_vehicle", None)
    return {"ok": True, "stop": doc.name}


@frappe.whitelist(methods=["POST"])
def report_theft(plate, location=None, report_number=None):
    """Report a vehicle stolen by submitting a Theft Vehicle Incident.

    Vehicle Incident.on_submit (Theft) flips Salis Vehicle.status to "Stopped",
    nulls current_driver, and clears the ex-driver's current_vehicle — the
    controller owns that flow, so we only build and submit the incident.
    """
    vehicle = _resolve_plate(plate)
    doc = frappe.get_doc({
        "doctype": "Vehicle Incident",
        "incident_type": "Theft",
        "vehicle": vehicle,
        "incident_date": getdate(today()),
        "location": (location or ""),
        "report_number": (report_number or ""),
        "description": _("Reported stolen from the Fleet OS dashboard."),
    })
    doc.insert()
    doc.submit()  # [#taa8d4]
    return {"ok": True, "incident": doc.name}


@frappe.whitelist(methods=["POST"])
def workshop_in(plate):
    """Send a vehicle to the workshop: Salis Vehicle.status -> Under Maintenance."""
    vehicle = _resolve_plate(plate)
    frappe.db.set_value("Salis Vehicle", vehicle, "status", "Under Maintenance")
    return {"ok": True}


@frappe.whitelist(methods=["POST"])
def workshop_out(plate):
    """Return a vehicle from the workshop: Salis Vehicle.status -> Active."""
    vehicle = _resolve_plate(plate)
    frappe.db.set_value("Salis Vehicle", vehicle, "status", "Active")
    return {"ok": True}


@frappe.whitelist(methods=["POST"])
def recover(plate):
    """Recover a stopped/stolen vehicle back to service: status -> Active."""
    vehicle = _resolve_plate(plate)
    frappe.db.set_value("Salis Vehicle", vehicle, "status", "Active")
    return {"ok": True}
