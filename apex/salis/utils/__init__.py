# Copyright (c) 2026, afmcoltd
"""Shared Salis helpers: vehicle locking, quota lookup, timeline notes and task raising.

``raise_rider_clearance_task`` inserts with ``ignore_permissions`` because it writes a **ToDo** —
the framework's own assignment record — on behalf of the flow rather than the caller. Granting a
role create on ToDo to satisfy it would let that role assign work to anyone on the site.
"""

import frappe
from frappe import _
from frappe.utils import getdate, today

from apex.apex_core.utils.portal_identity import (
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

	Shared by the fleet self-service reads and writes so vehicle scope cannot drift.
	"""
    vehicle = frappe.db.get_value("Salis Driver", driver, "current_vehicle")
    if vehicle:
        return vehicle
    return frappe.db.get_value(
        "Vehicle Assignment", {"driver": driver, "status": "Active", "docstatus": 1}, "vehicle"
    )

def vehicle_is_held_out_of_service(vehicle):
    """The name of the record holding ``vehicle`` off the road, or None.

    ``SalisVehicle`` already refuses an operator's own status edit while a stop or an
    open incident owns the vehicle; this answers the same question for the machine
    writers, which reach the row through ``frappe.db.set_value`` and never run that
    controller. The two must agree, so the conditions here are the ones
    ``_refuse_a_status_edit_while_a_stop_owns_the_vehicle`` reads."""
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
    """Stamp the vehicle's driver pairing together with the login-user mirror beside it.

	``Salis Vehicle.current_driver_user`` is a ``fetch_from`` mirror of
	``current_driver.driver_user``, and the framework resolves ``fetch_from`` only inside
	``BaseDocument._validate_links`` (frappe/model/base_document.py:849-851), which runs
	on the ORM save path. Every sanctioned writer of this pairing is a
	``frappe.db.set_value`` — deliberately, because ``SalisVehicle`` refuses a
	hand-written ``current_driver`` — and ``set_value`` runs no controller and no fetch
	(frappe/database/database.py:942-945). Left to the framework the mirror therefore
	moves only when something unrelated happens to save the vehicle, so it is written
	here instead. The driver-facing compliance Notification addresses that mirror, and a
	STALE one is worse than an empty one: it mails the vehicle's previous driver.

	``vehicle`` is required; ``driver`` may be None to clear the pairing. Extra vehicle
	fields for the same write are passed through as keyword arguments.
	"""
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
	every open Active Vehicle Assignment for the vehicle, clears each outgoing driver
	mirror, then inserts + submits a new one. ``VehicleAssignment.on_submit`` stamps
	the new Salis Vehicle.current_driver and Salis Driver.current_vehicle pair. Callers own
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

_TR_TERMINAL = {"Fulfilled", "Cancelled"}

_CLEARANCE_SAVEPOINT = "apex_salis_rider_clearance"

def _workflow_source_states(action):
    """The states the native Transport Request Workflow lists as sources for ``action``.

    Read off the Workflow record rather than copied into this module: a duplicate of a
    governance table is the one that drifts."""
    from frappe.model.workflow import get_workflow_name

    workflow = get_workflow_name("Transport Request")
    if not workflow:
        return set()
    return {
        row.state
        for row in frappe.get_doc("Workflow", workflow).transitions
        if row.action == action
    }

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
	2. Otherwise fall back to a direct write of ``target_state`` (and
	   ``extra_fields``) — but ONLY from a state the Workflow itself lists as a
	   source for ``action``. This covers the case where the Movement user who
	   submits the Route Plan / Dispatch Trip does not personally hold the
	   transition role, so the operational chain never deadlocks on a permission
	   gap. It does not cover skipping the transition's own place in the chain.

	The fallback writes ``status`` and nothing else. A private copy of the Workflow's
	state -> doc_status map, writing ``docstatus`` from it, turns a permission gap into
	a submit: a Fleet Manager who cannot authorize their own request could submit a
	Route Plan naming it and land it at Scheduled / docstatus 1 with no Authorize
	transition, no Workflow Action row and no ``before_submit``. Every transition this
	helper is used for moves between two
	states of the SAME doc_status, so there is nothing legitimate for it to write; a
	docstatus change belongs on the native path.

	Terminal requests (Fulfilled / Cancelled) are left untouched. Returns the
	state the request now holds (or None when skipped or refused).
	"""
    if not tr_name:
        return None

    current = frappe.db.get_value("Transport Request", tr_name, "status")
    if current in _TR_TERMINAL:
        return None
    if current == target_state:
        return current

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
    """System reversal of a Transport Request state (e.g. when the Dispatch Trip
	that fulfilled it is cancelled).

	A native Workflow is forward-only — it has no backward transition — so an
	automated reversal cannot go through ``apply_workflow``. This guarded direct
	write rolls the request back to ``to_state`` only when it is still in
	``from_state`` and (optionally) still tied to ``dispatch_trip``, keeping the
	docstatus consistent with the workflow's state map. Both reversal states are
	docstatus 1 (Scheduled <- Fulfilled), so the document stays submitted.

	``clear_fields`` nulls a field; ``reset_fields`` sets one to an explicit value.
	A Check field needs the second — NULL is not 0 to a filter, so a request whose
	``is_assigned`` is nulled rather than zeroed still reads as assigned.

	``docstatus`` is not written here either: both reversal states are doc_status 1
	(Scheduled <- Fulfilled), so there is nothing for it to change.
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
    """Return a human-readable reason the rider must NOT receive a vehicle/fuel,
	or ``None`` when the rider is clear.

	Given a Salis Driver name, this resolves the linked HRMS Employee and reports
	the first blocking condition found, in priority order:

	1. The linked Employee is Inactive / Left / Suspended.
	2. The Employee has an approved Leave Application covering ``on_date``
	   (default: today).
	3. The Salis Driver's own status is Stopped / Released.

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
    """Return the name of an Approved, submitted Leave Application for ``employee``
	whose period covers ``on_date``, else ``None``."""
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
    """Open a clearance/settlement task for the Movement Supervisor to
	recover the vehicle + custody from a rider who is on leave / inactive but
	still holds a vehicle.

	Native primitive: ``frappe.desk.form.assign_to.add`` — the standard "actionable
	item owned by a person" call, not a raw ``ToDo`` insert, so the bell and email
	notification the ToDo controller does not send on its own still reach the
	supervisor.

	Assignee resolution (first that yields a user):
	  1. The supervisor on the driver's current Vehicle Assignment.
	  2. The ``supervisor`` recorded on the Salis Driver master.
	  3. Every enabled holder of the ``Fleet Supervisor`` role who can see the
	     driver's own project (``apex.salis.permissions.report_project_scope``) —
	     an out-of-scope supervisor is never handed a task whose link they cannot
	     open.

	Idempotent: keyed on an open ToDo for the same driver (``reference_type`` =
	Salis Driver, ``reference_name`` = driver) — re-running never spawns a second
	task while one is still open. Best-effort: a failure is logged and swallowed
	so it can never abort the guarded transaction (the delivery is already being
	rejected; the task is a follow-up).

	Returns the list of ToDo names created (possibly empty).
	"""
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

        from frappe.desk.form import assign_to as _assign_to

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
    """Resolve the Movement Supervisor user(s) for a driver's clearance task.

	Prefers the per-record supervisor (Vehicle Assignment, then Salis Driver
	master) and falls back to the Fleet Supervisor role holders scoped to the
	driver's own project — the same project scope ``apex.salis.permissions``
	enforces everywhere else, so this fallback cannot hand a task to a
	supervisor who could not open the driver it names. Administrator / Guest
	and disabled users are filtered out."""
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
        return
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Salis: timeline note failed")

def set_financial_defaults(doc):
    """Default company and cost center from Salis Settings for reporting and
	financial context. Reference fields only - no GL/Payment Entry is posted."""
    from apex.apex_core.doctype.salis_settings.salis_settings import (
        get_default_cost_center,
    )
    from apex.apex_core.utils.company import resolve_company

    if not doc.company:
        doc.company = resolve_company("Salis")
    if not doc.cost_center:
        doc.cost_center = get_default_cost_center()

def validate_vehicle_compliance(doc):
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

def worker_was_on_trip(employee, dispatch_trip):
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
       Passenger`` rows.

    A pure data check with no session dependency, so it is shared by the worker
    portal's rating endpoint (which resolves WHO ``employee`` is from the caller's
    token) and Transport Trip Rating's own ``validate`` (which only knows the
    field value already on the record).
    """
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
