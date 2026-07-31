# Copyright (c) 2026, AFMCO and contributors
# [#2ksmt5]

import frappe
from frappe import _
from frappe.utils import getdate, today

from apex.apex_core.utils.portal_token_security import (
    DRIVER,
    presented_token,
    resolve_portal_subject,
)


def get_driver_for_user(user=None):
    """Return the Salis Driver for the caller, or None.

	A presented driver credential always takes precedence and either resolves or
	raises. Only a request with no driver credential may use the legacy explicit or
	session User preview path. Callers that intentionally authorize only a Frappe User
	must use ``get_driver_for_session_user`` so a request cookie cannot change their
	authority."""
    raw, was_presented = presented_token(DRIVER)
    if was_presented:
        return resolve_portal_subject(DRIVER, raw, required=True)
    return get_driver_for_session_user(user)


def get_driver_for_session_user(user=None):
    """Resolve only User -> Employee -> Salis Driver, ignoring portal cookies."""
    user = user or frappe.session.user
    employee = frappe.db.get_value("Employee", {"user_id": user}, "name")
    if not employee:
        return None
    return frappe.db.get_value("Salis Driver", {"employee": employee}, "name")


def has_any_role(user, roles):
    """True when ``user`` holds any role in ``roles``; Administrator always True.

	The membership TEST only — every caller keeps its own role tuple, because the
	sets are deliberately not the same (the boarding scan gate excludes Finance
	Manager, the driver-portal display hint includes it). Sharing the test without
	sharing the set is what stops a copy of this three-liner drifting again.
	"""
    user = user or frappe.session.user
    if user == "Administrator":
        return True
    return bool(set(frappe.get_roles(user)) & set(roles))


def bound_vehicle(driver):
    """The vehicle bound to ``driver`` (current_vehicle, else Active Assignment), or None.

	The single read-side binding rule, deliberately kept in one place beside the
	driver resolvers: it must stay identical to the write-side check fuel requests
	enforce (``driver_portal.fuel._vehicle_bound_to_driver``), so a drift between a
	portal read and a fuel write would be a permission bug, not a cosmetic one.
	"""
    vehicle = frappe.db.get_value("Salis Driver", driver, "current_vehicle")
    if vehicle:
        return vehicle
    return frappe.db.get_value(
        "Vehicle Assignment", {"driver": driver, "status": "Active"}, "vehicle"
    )


def lock_vehicle(name):
    """Row-lock a Salis Vehicle to prevent concurrent assignment/handover races."""
    if name:
        Vehicle = frappe.qb.DocType("Salis Vehicle")
        frappe.qb.from_(Vehicle).select(Vehicle.name).where(Vehicle.name == name).for_update().run()


def lock_driver(name):
    """Row-lock a Salis Driver."""
    if name:
        Driver = frappe.qb.DocType("Salis Driver")
        frappe.qb.from_(Driver).select(Driver.name).where(Driver.name == name).for_update().run()


def lock_fuel_quota(name):
    """Row-lock a Fuel Quota to serialize quota consumption/reversal."""
    if name:
        FuelQuota = frappe.qb.DocType("Fuel Quota")
        frappe.qb.from_(FuelQuota).select(FuelQuota.name).where(
            FuelQuota.name == name
        ).for_update().run()


def period_quota(vehicle, period_month, fields):
    """The live Fuel Quota row for ``vehicle`` in ``period_month``, or None.

	One resolver behind every fuel door — the driver portal and the /fleet employee
	page — so the quota bar a rider sees and the allowance their request is held to
	can never name different rows. It lives here, beside ``lock_fuel_quota``, because
	both callers already depend on this package; a copy inside either endpoint module
	would make the other import a private name across packages.

	``docstatus < 2`` keeps a draft or submitted allocation and drops a cancelled one
	— the same scope the Fuel Quota duplicate guard treats as live, so at most one
	row can match a (vehicle, period) pair. A vehicle with NO allocation that month
	yields None, which is not a refusal: the allocation is what creates a ceiling, so
	the caller binds an empty ``fuel_quota`` and the controller's allowance gate
	returns at its first line."""
    if not vehicle:
        return None
    return frappe.db.get_value(
        "Fuel Quota",
        {"vehicle": vehicle, "period_month": period_month, "docstatus": ["<", 2]},
        fields,
        as_dict=True,
    )


def normalize_plate(plate):
    """Canonical plate key: strip all whitespace and upper-case.

	The single normaliser behind ``Salis Vehicle.plate_normalized`` and every
	plate lookup, so a plate written with different spacing/case still resolves
	to one vehicle. Callers own their own None/empty guard before calling."""
    return "".join(str(plate).split()).upper()


def expiry_state(expiry_date, warn_days):
    """Signed days-to-expiry plus a near-/over-expiry state for an expiry date.

	Returns ``(days, state)`` where ``days = date_diff(expiry_date, today)`` (a
	signed int; negative = already expired) and ``state`` is ``expired`` (days <
	0) | ``expiring`` (days <= ``warn_days``) | ``valid``. Computed server-side so
	the driver/masar SPAs need no date math and both languages render identically."""
    days = frappe.utils.date_diff(expiry_date, frappe.utils.getdate())
    state = "expired" if days < 0 else ("expiring" if days <= warn_days else "valid")
    return days, state


def days_until(value):
    """Whole days from today until ``value`` (a date), or None.

	Defensive: a missing or unparseable value degrades to None rather than
	raising, so an identity-document expiry that is blank/malformed never aborts
	a profile render."""
    if not value:
        return None
    try:
        return frappe.utils.date_diff(value, frappe.utils.today())
    except Exception:
        return None


def reassign_vehicle_driver(vehicle, driver, start_date=None, reject_same_driver=False):
    """End the vehicle's open Active assignment(s) and start a new submitted one.

	The single native reassign operation shared by both supervisor surfaces (the
	/fleet board and the Fleet Control drawer) so they can never diverge: ends
	every open Active Vehicle Assignment for the vehicle, then inserts + submits a
	new one. ``VehicleAssignment.on_submit`` is what stamps Salis Vehicle.current_driver
	and Salis Driver.current_vehicle (controllers are not bypassed). Callers own
	their own input resolution (plate->vehicle, external driver_id->driver) and
	permission checks before calling. Returns the new assignment name.

	``reject_same_driver`` throws when the vehicle is already assigned to ``driver``
	(the drawer rejects a no-op reassign; the board allows a refresh)."""
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
    """Close an open submitted Vehicle Suspension through the native cancel lifecycle.

	The single native stop-close operation shared by both supervisor surfaces:
	stamps the workshop-exit audit fields (return_date / released_on / released_by)
	on the submitted stop, then cancels it so ``VehicleStop.on_cancel`` runs the
	reversal (the vehicle is not poked directly). Callers locate their own stop
	(plain stop vs the open Maintenance stop) and re-check permission first."""
    on = getdate(today())
    ret = getdate(return_date) if return_date else on
    frappe.db.set_value(
        "Vehicle Suspension",
        stop_name,
        {"return_date": ret, "released_on": on, "released_by": frappe.session.user},
    )
    frappe.get_doc("Vehicle Suspension", stop_name).cancel()


# [#tqf298]
_TR_STATE_DOCSTATUS = {
    "New": 0,
    "Validated": 0,
    "Approved": 1,
    "Scheduled": 1,
    "Fulfilled": 1,
    "Rejected": 0,
    "Cancelled": 2,
}

# [#6jujlr]
_TR_TERMINAL = {"Fulfilled", "Cancelled"}

# Distinct from habitat's notify savepoint: both can be live in one request, and a
# shared name would let one helper's rollback destroy the other's mark.
_CLEARANCE_SAVEPOINT = "apex_salis_rider_clearance"


def drive_transport_request(tr_name, action, target_state, extra_fields=None):
    """Advance a Transport Request from a related Movement document.

	The Transport Request status field is owned by the native Transport Request
	Workflow. Route Plan (-> Scheduled) and Dispatch Trip (-> Fulfilled) drive
	that state as a side effect of their own submit. This helper keeps the
	workflow state consistent:

	1. If a workflow transition named ``action`` is currently available to the
	   acting user on the Transport Request, apply it via
	   ``frappe.model.workflow.apply_workflow`` (the framework-owned path —
	   bumps docstatus, writes the Workflow comment, runs conditions).
	2. Otherwise fall back to a guarded direct write of ``target_state`` (and
	   ``extra_fields``) that is consistent with the workflow's state ->
	   docstatus map. This covers the case where the Movement user who submits
	   the Route Plan / Dispatch Trip does not personally hold the transition
	   role, so the operational chain never deadlocks on a permission gap.

	Terminal requests (Fulfilled / Cancelled) are left untouched. Returns the
	state the request now holds (or None when skipped).
	"""
    if not tr_name:
        return None

    current = frappe.db.get_value("Transport Request", tr_name, "status")
    if current in _TR_TERMINAL:
        return None
    if current == target_state:
        return current

    # [#75w6jt]
    try:
        from frappe.model.workflow import apply_workflow, get_transitions, get_workflow_name

        if get_workflow_name("Transport Request"):
            tr_doc = frappe.get_doc("Transport Request", tr_name)
            available = {t.action for t in get_transitions(tr_doc)}
            if action in available:
                apply_workflow(tr_doc, action)
                if extra_fields:
                    frappe.db.set_value("Transport Request", tr_name, extra_fields)
                return target_state
    except Exception:
        # [#4epfxd]
        frappe.log_error(
            frappe.get_traceback(), "Salis: workflow drive fell back to direct write"
        )

    # [#lls5rg]
    values = {"status": target_state}
    if extra_fields:
        values.update(extra_fields)

    target_docstatus = _TR_STATE_DOCSTATUS.get(target_state)
    if target_docstatus is not None:
        # [#daqwvk]
        values["docstatus"] = target_docstatus

    frappe.db.set_value("Transport Request", tr_name, values)
    add_timeline_note(
        "Transport Request",
        tr_name,
        _("Status advanced to {0} by {1}.").format(target_state, action),
    )
    return target_state


def revert_transport_request(tr_name, from_state, to_state, dispatch_trip=None, clear_fields=None):
    """System reversal of a Transport Request state (e.g. when the Dispatch Trip
	that fulfilled it is cancelled).

	A native Workflow is forward-only — it has no backward transition — so an
	automated reversal cannot go through ``apply_workflow``. This guarded direct
	write rolls the request back to ``to_state`` only when it is still in
	``from_state`` and (optionally) still tied to ``dispatch_trip``, keeping the
	docstatus consistent with the workflow's state map. Both reversal states are
	docstatus 1 (Scheduled <- Fulfilled), so the document stays submitted.
	"""
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
    target_docstatus = _TR_STATE_DOCSTATUS.get(to_state)
    if target_docstatus is not None:
        values["docstatus"] = target_docstatus

    frappe.db.set_value("Transport Request", tr_name, values)
    add_timeline_note(
        "Transport Request",
        tr_name,
        _("Status reverted from {0} to {1}.").format(from_state, to_state),
    )
    return to_state


# [#pbj851]

# [#kdkk0c]
INACTIVE_EMPLOYEE_STATUSES = ("Inactive", "Left", "Suspended")

# [#9kwn9b]
BLOCKING_DRIVER_STATUSES = ("Stopped", "On Leave", "Released")


def rider_block_reason(driver, on_date=None):
    """Return a human-readable reason the rider must NOT receive a vehicle/fuel,
	or ``None`` when the rider is clear.

	Given a Salis Driver name, this resolves the linked HRMS Employee and reports
	the first blocking condition found, in priority order:

	1. The linked Employee is Inactive / Left / Suspended.
	2. The Employee has an approved Leave Application covering ``on_date``
	   (default: today).
	3. The Salis Driver's own status is Stopped / On Leave / Released.

	The returned string is already wrapped with ``_()`` and names the driver so a
	caller can ``frappe.throw`` it directly. Read-only and side-effect free.
	"""
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

    # [#2xlsof]
    if drv.employee:
        emp_status = frappe.db.get_value("Employee", drv.employee, "status")
        if emp_status in INACTIVE_EMPLOYEE_STATUSES:
            return _("Rider {0} is {1} in their Employee record and cannot receive a vehicle or fuel.").format(
                label, _(emp_status)
            )

        # [#dnxa0n]
        leave = _approved_leave_on(drv.employee, on_date)
        if leave:
            return _(
                "Rider {0} is on approved leave ({1}) covering {2} and cannot receive a vehicle or fuel."
            ).format(label, leave, on_date)

    # [#2gphk9]
    if drv.status in BLOCKING_DRIVER_STATUSES:
        return _("Rider {0} is marked {1} and cannot receive a vehicle or fuel.").format(
            label, _(drv.status)
        )

    return None


def _approved_leave_on(employee, on_date):
    """Return the name of an Approved, submitted Leave Application for ``employee``
	whose period covers ``on_date``, else ``None``.

	Defensive: HRMS may not be installed (the Leave Application DocType is absent)
	on a given bench, so a lookup failure degrades to "no leave" rather than
	aborting the delivery guard."""
    if not employee:
        return None
    try:
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
    except Exception:
        # [#ififlm]
        return None
    return rows[0] if rows else None


def raise_rider_clearance_task(driver, vehicle=None, source_doctype=None, source_name=None):
    """Open a clearance/settlement task for the Movement Supervisor to
	recover the vehicle + custody from a rider who is on leave / inactive but
	still holds a vehicle.

	Native primitive: a Frappe **ToDo** assigned to the supervisor — the standard
	"actionable item owned by a person" object, surfaced on their desk and in the
	assignment badge. The Operations Alert DocType is intentionally NOT used here:
	its ``alert_type`` enum (Idle Vehicle / Forgotten Request / ... ) has no
	recovery/clearance type, and that enum lives in apex_core.

	Assignee resolution (first that yields a user):
	  1. The supervisor on the driver's current Vehicle Assignment.
	  2. The ``supervisor`` recorded on the Salis Driver master.
	  3. Every enabled holder of the ``Fleet Supervisor`` role.

	Idempotent: keyed on an open ToDo for the same driver (``reference_type`` =
	Salis Driver, ``reference_name`` = driver) — re-running never spawns a second
	task while one is still open. Best-effort: a failure is logged and swallowed
	so it can never abort the guarded transaction (the delivery is already being
	rejected; the task is a follow-up).

	Returns the list of ToDo names created (possibly empty).
	"""
    if not driver:
        return []

    # The docstring's "can never abort the guarded transaction" promise needs a SAVEPOINT:
    # a bare frappe.db.rollback() discards the caller's whole transaction, including the
    # rejection this follow-up task is meant to accompany.
    frappe.db.savepoint(_CLEARANCE_SAVEPOINT)
    try:
        # [#q5qqgf]
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
        # [#70vv14]
        assignees = [u for u in assignees if u not in existing]
        if not assignees:
            return []

        label = frappe.db.get_value("Salis Driver", driver, "full_name") or driver
        veh = vehicle or frappe.db.get_value("Salis Driver", driver, "current_vehicle")
        description = _(
            "Clearance required: rider {0} is on leave/inactive but still holds vehicle {1}. "
            "Recover the vehicle and custody."
        ).format(label, veh or _("n/a"))

        created = []
        for user in assignees:
            todo = frappe.get_doc(
                {
                    "doctype": "ToDo",
                    "allocated_to": user,
                    "reference_type": "Salis Driver",
                    "reference_name": driver,
                    "description": description,
                    "priority": "High",
                    "assigned_by": frappe.session.user,
                }
            ).insert(ignore_permissions=True)  # audit-ok
            created.append(todo.name)

        # [#lg7hm5]
        if source_doctype and source_name:
            add_timeline_note(source_doctype, source_name, description)

        return created
    except Exception:
        frappe.db.rollback(save_point=_CLEARANCE_SAVEPOINT)
        frappe.log_error(frappe.get_traceback(), "Salis: rider clearance task failed")
        return []


def _clearance_assignees(driver):
    """Resolve the Movement Supervisor user(s) for a driver's clearance task.

	Prefers the per-record supervisor (Vehicle Assignment, then Salis Driver
	master) and falls back to the Fleet Supervisor role holders. Administrator /
	Guest and disabled users are filtered out."""
    candidates = []

    # [#saojkk]
    assignment_sup = frappe.get_all(
        "Vehicle Assignment",
        filters={"driver": driver, "docstatus": 1, "status": "Active"},
        fields=["supervisor"],
        order_by="modified desc",
        limit=1,
    )
    if assignment_sup and assignment_sup[0].supervisor:
        candidates.append(assignment_sup[0].supervisor)

    # [#5x4vod]
    driver_sup = frappe.db.get_value("Salis Driver", driver, "supervisor")
    if driver_sup:
        candidates.append(driver_sup)

    # [#fsf12q]
    if not candidates:
        candidates = frappe.get_all(
            "Has Role",
            filters={"role": "Fleet Supervisor", "parenttype": "User"},
            pluck="parent",
        )

    # [#ep9yz7]
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
    """Record a human-readable note on a related document's timeline.

	Thin, best-effort wrapper around the native ``add_comment`` so a cross-document
	audit note (e.g. a Fuel Request annotating its Fuel Quota) lands on the target
	doc's own timeline. The write must never abort the parent transaction, so any
	failure is swallowed and logged. Create/submit/cancel/field changes on the
	parent itself are already captured natively by Version (track_changes) and the
	automatic comments, so this is only for notes about a *different* document.
	"""
    if not (doctype and name):
        return
    try:
        frappe.get_doc(doctype, name).add_comment("Info", message)
    except frappe.DoesNotExistError:
        # [#j2mvqv]
        return
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Salis: timeline note failed")


def set_financial_defaults(doc):
    """Default company and cost center from Salis Settings for reporting and
	financial context. Reference fields only - no GL/Payment Entry is posted."""
    from apex.apex_core.doctype.salis_settings.salis_settings import (
        get_default_company,
        get_default_cost_center,
    )

    if not doc.company:
        doc.company = get_default_company()
    if not doc.cost_center:
        doc.cost_center = get_default_cost_center()


def enforce_vehicle_compliance(doc):
    """Block (or warn) when the linked vehicle's compliance has expired.

	Reads Salis Vehicle.compliance_status; if Expired, honours the
	Salis Settings.block_assignment_on_expired_compliance flag: block when
	set, otherwise warn. Safe default = warn.
	"""
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
