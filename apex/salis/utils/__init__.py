# Copyright (c) 2026, afmcoltd

import frappe
from frappe import _
from frappe.desk.form import assign_to as _assign_to
from frappe.model.workflow import apply_workflow, get_transitions, get_workflow_name
from frappe.utils import getdate, today

from apex.apex_core.doctype.salis_settings.salis_settings import get_default_cost_center
from apex.apex_core.utils.company import resolve_company
from apex.apex_core.utils.portal_identity import (
    DRIVER,
    presented_token,
    resolve_portal_subject,
)

def get_driver_for_user(user=None):
    raw, was_presented = presented_token(DRIVER)
    if was_presented:
        return resolve_portal_subject(DRIVER, raw, required=True)
    return get_driver_for_session_user(user)

def get_driver_for_session_user(user=None):
    user = user or frappe.session.user
    employee = frappe.db.get_value("Employee", {"user_id": user}, "name")
    if not employee:
        return None
    return frappe.db.get_value("Salis Driver", {"employee": employee}, "name")

def has_any_role(user, roles):
    user = user or frappe.session.user
    if user == "Administrator":
        return True
    return bool(set(frappe.get_roles(user)) & set(roles))

def bound_vehicle(driver):
    vehicle = frappe.db.get_value("Salis Driver", driver, "current_vehicle")
    if vehicle:
        return vehicle
    return frappe.db.get_value(
        "Vehicle Assignment", {"driver": driver, "status": "Active", "docstatus": 1}, "vehicle"
    )

def vehicle_is_held_out_of_service(vehicle):
    if not vehicle:
        return None
    return frappe.db.exists(
        "Vehicle Suspension",
        {"vehicle": vehicle, "docstatus": 1, "return_date": ["is", "not set"]},
    ) or frappe.db.exists(
        "Vehicle Incident",
        {"vehicle": vehicle, "docstatus": 1, "status": ["in", ("Open", "Under Review")]},
    )

def set_current_driver(vehicle, driver, update_modified=True, **extra_values):
    if not vehicle:
        return
    values = {
        "current_driver": driver,
        "current_driver_user": (
            frappe.db.get_value("Salis Driver", driver, "driver_user") if driver else None
        ),
    }
    values.update(extra_values)
    frappe.db.set_value("Salis Vehicle", vehicle, values, update_modified=update_modified)

def lock_vehicle(name):
    if name:
        Vehicle = frappe.qb.DocType("Salis Vehicle")
        frappe.qb.from_(Vehicle).select(Vehicle.name).where(Vehicle.name == name).for_update().run()

def lock_driver(name):
    if name:
        Driver = frappe.qb.DocType("Salis Driver")
        frappe.qb.from_(Driver).select(Driver.name).where(Driver.name == name).for_update().run()

def lock_fuel_quota(name):
    if name:
        FuelQuota = frappe.qb.DocType("Fuel Quota")
        frappe.qb.from_(FuelQuota).select(FuelQuota.name).where(
            FuelQuota.name == name
        ).for_update().run()

def period_quota(vehicle, period_month, fields):
    if not vehicle:
        return None
    return frappe.db.get_value(
        "Fuel Quota",
        {"vehicle": vehicle, "period_month": period_month, "docstatus": ["<", 2]},
        fields,
        as_dict=True,
    )

def normalize_plate(plate):
    return "".join(str(plate).split()).upper()

def days_until(value):
    if not value:
        return None
    try:
        return frappe.utils.date_diff(value, frappe.utils.today())
    except Exception:
        return None

def reassign_vehicle_driver(vehicle, driver, start_date=None, reject_same_driver=False):
    lock_vehicle(vehicle)
    lock_driver(driver)
    start = getdate(start_date) if start_date else getdate(today())

    for r in frappe.get_all(
        "Vehicle Assignment",
        filters={"vehicle": vehicle, "status": "Active", "docstatus": 1},
        fields=["name", "driver"],
    ):
        if reject_same_driver and r.driver == driver:
            frappe.throw(
                _("Vehicle {0} is already assigned to driver {1}.").format(vehicle, driver)
            )
        frappe.db.set_value("Vehicle Assignment", r.name, {"status": "Ended", "end_date": start})
        if frappe.db.get_value("Salis Driver", r.driver, "current_vehicle") == vehicle:
            frappe.db.set_value("Salis Driver", r.driver, "current_vehicle", None)

    assignment = frappe.get_doc({
        "doctype": "Vehicle Assignment",
        "vehicle": vehicle,
        "driver": driver,
        "project": frappe.db.get_value("Salis Vehicle", vehicle, "project"),
        "start_date": start,
        "status": "Active",
    })
    assignment.insert()
    assignment.submit()
    return assignment.name

def close_open_stop(stop_name, return_date=None):
    on = getdate(today())
    ret = getdate(return_date) if return_date else on
    frappe.db.set_value(
        "Vehicle Suspension",
        stop_name,
        {"return_date": ret, "released_on": on, "released_by": frappe.session.user},
    )
    frappe.get_doc("Vehicle Suspension", stop_name).cancel()

_TR_TERMINAL = {"Fulfilled", "Cancelled"}

_CLEARANCE_SAVEPOINT = "apex_salis_rider_clearance"

def _workflow_source_states(action):
    workflow = get_workflow_name("Transport Request")
    if not workflow:
        return set()
    return {
        row.state
        for row in frappe.get_doc("Workflow", workflow).transitions
        if row.action == action
    }

def drive_transport_request(tr_name, action, target_state, extra_fields=None):
    if not tr_name:
        return None

    current = frappe.db.get_value("Transport Request", tr_name, "status")
    if current in _TR_TERMINAL:
        return None
    if current == target_state:
        return current

    try:
        if get_workflow_name("Transport Request"):
            tr_doc = frappe.get_doc("Transport Request", tr_name)
            available = {t.action for t in get_transitions(tr_doc)}
            if action in available:
                apply_workflow(tr_doc, action)
                if extra_fields:
                    frappe.db.set_value("Transport Request", tr_name, extra_fields)
                return target_state
    except Exception:
        frappe.log_error(
            frappe.get_traceback(), "Salis: workflow drive fell back to direct write"
        )

    if current not in _workflow_source_states(action):
        frappe.logger("salis").warning(
            f"drive_transport_request refused {tr_name}: {action} has no source state "
            f"{current} in the Transport Request Workflow"
        )
        return None

    values = {"status": target_state}
    if extra_fields:
        values.update(extra_fields)

    frappe.db.set_value("Transport Request", tr_name, values)
    add_timeline_note(
        "Transport Request",
        tr_name,
        _("Status advanced to {0} by {1}.").format(target_state, action),
    )
    return target_state

def revert_transport_request(
    tr_name, from_state, to_state, dispatch_trip=None, clear_fields=None, reset_fields=None
):
    if not tr_name:
        return None
    tr = frappe.db.get_value(
        "Transport Request", tr_name, ["status", "dispatch_trip"], as_dict=True
    )
    if not tr or tr.status != from_state:
        return None
    if dispatch_trip is not None and tr.dispatch_trip != dispatch_trip:
        return None

    values = {"status": to_state}
    for fieldname in (clear_fields or []):
        values[fieldname] = None
    values.update(reset_fields or {})

    frappe.db.set_value("Transport Request", tr_name, values)
    add_timeline_note(
        "Transport Request",
        tr_name,
        _("Status reverted from {0} to {1}.").format(from_state, to_state),
    )
    return to_state

INACTIVE_EMPLOYEE_STATUSES = ("Inactive", "Left", "Suspended")

BLOCKING_DRIVER_STATUSES = ("Stopped", "Released")

def rider_block_reason(driver, on_date=None):
    if not driver:
        return None

    on_date = getdate(on_date) if on_date else getdate(today())

    drv = frappe.db.get_value(
        "Salis Driver",
        driver,
        ["full_name", "employee", "status"],
        as_dict=True,
    )
    if not drv:
        return None

    label = drv.full_name or driver

    if drv.employee:
        emp_status = frappe.db.get_value("Employee", drv.employee, "status")
        if emp_status in INACTIVE_EMPLOYEE_STATUSES:
            return _("Rider {0} is {1} in their Employee record and cannot receive a vehicle or fuel.").format(
                label, _(emp_status)
            )

        leave = _approved_leave_on(drv.employee, on_date)
        if leave:
            return _(
                "Rider {0} is on approved leave ({1}) covering {2} and cannot receive a vehicle or fuel."
            ).format(label, leave, on_date)

    if drv.status in BLOCKING_DRIVER_STATUSES:
        return _("Rider {0} is marked {1} and cannot receive a vehicle or fuel.").format(
            label, _(drv.status)
        )

    return None

def _approved_leave_on(employee, on_date):
    if not employee:
        return None
    rows = frappe.get_all(
        "Leave Application",
        filters={
            "employee": employee,
            "status": "Approved",
            "docstatus": 1,
            "from_date": ["<=", on_date],
            "to_date": [">=", on_date],
        },
        pluck="name",
        limit=1,
    )
    return rows[0] if rows else None

def raise_rider_clearance_task(driver, vehicle=None, source_doctype=None, source_name=None):
    if not driver:
        return []

    frappe.db.savepoint(_CLEARANCE_SAVEPOINT)
    try:
        existing = frappe.get_all(
            "ToDo",
            filters={
                "reference_type": "Salis Driver",
                "reference_name": driver,
                "status": "Open",
            },
            pluck="allocated_to",
        )

        assignees = _clearance_assignees(driver)
        assignees = [u for u in assignees if u not in existing]
        if not assignees:
            return []

        label = frappe.db.get_value("Salis Driver", driver, "full_name") or driver
        veh = vehicle or frappe.db.get_value("Salis Driver", driver, "current_vehicle")
        description = _(
            "Clearance required: rider {0} is on leave/inactive but still holds vehicle {1}. "
            "Recover the vehicle and custody."
        ).format(label, veh or _("n/a"))

        _assign_to.add(
            {
                "doctype": "Salis Driver",
                "name": driver,
                "assign_to": assignees,
                "description": description,
                "priority": "High",
                "assigned_by": frappe.session.user,
            },
            ignore_permissions=True,
        )
        created = frappe.get_all(
            "ToDo",
            filters={
                "reference_type": "Salis Driver",
                "reference_name": driver,
                "allocated_to": ["in", assignees],
                "status": "Open",
            },
            pluck="name",
        )

        if source_doctype and source_name:
            add_timeline_note(source_doctype, source_name, description)

        return created
    except Exception:
        frappe.db.rollback(save_point=_CLEARANCE_SAVEPOINT)
        frappe.log_error(frappe.get_traceback(), "Salis: rider clearance task failed")
        return []

def _clearance_assignees(driver):
    candidates = []

    assignment_sup = frappe.get_all(
        "Vehicle Assignment",
        filters={"driver": driver, "docstatus": 1, "status": "Active"},
        fields=["supervisor"],
        order_by="modified desc",
        limit=1,
    )
    if assignment_sup and assignment_sup[0].supervisor:
        candidates.append(assignment_sup[0].supervisor)

    driver_sup = frappe.db.get_value("Salis Driver", driver, "supervisor")
    if driver_sup:
        candidates.append(driver_sup)

    if not candidates:
        from apex.salis import permissions as salis_permissions

        project = frappe.db.get_value("Salis Driver", driver, "project")
        for user in frappe.get_all(
            "Has Role",
            filters={"role": "Fleet Supervisor", "parenttype": "User"},
            pluck="parent",
        ):
            restrict, allowed = salis_permissions.report_project_scope(user)
            if not restrict or (project and project in allowed):
                candidates.append(user)

    seen = []
    for user in candidates:
        if (
            user
            and user not in seen
            and user not in ("Administrator", "Guest")
            and frappe.db.get_value("User", user, "enabled")
        ):
            seen.append(user)
    return seen

def add_timeline_note(doctype, name, message):
    if not (doctype and name):
        return
    try:
        frappe.get_doc(doctype, name).add_comment("Info", message)
    except frappe.DoesNotExistError:
        return
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Salis: timeline note failed")

def set_financial_defaults(doc):
    if not doc.company:
        doc.company = resolve_company("Salis")
    if not doc.cost_center:
        doc.cost_center = get_default_cost_center()

def validate_vehicle_compliance(doc):
    if not doc.vehicle:
        return
    status = frappe.db.get_value("Salis Vehicle", doc.vehicle, "compliance_status")
    if status != "Expired":
        return
    if frappe.db.get_single_value(
        "Salis Settings", "block_assignment_on_expired_compliance"
    ):
        frappe.throw(
            _("Vehicle {0} has expired compliance and cannot be dispatched/assigned.").format(
                doc.vehicle
            )
        )
    else:
        frappe.msgprint(
            _("Warning: vehicle {0} has expired compliance.").format(doc.vehicle),
            indicator="orange",
        )

def worker_was_on_trip(employee, dispatch_trip):
    if not (employee and dispatch_trip):
        return False

    boarding = frappe.get_all(
        "Trip Boarding State",
        filters={"parent": dispatch_trip, "parenttype": "Dispatch Trip"},
        fields=["employee", "status"],
    )
    if boarding:
        return any(b.employee == employee and b.status == "Boarded" for b in boarding)

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
