# Shared server-side helpers for the Salis fleet module.
# Imported by Salis DocType controllers — keep side-effect free at import time.

import frappe
from frappe import _
from frappe.utils import getdate, today


def lock_vehicle(name):
	"""Row-lock a Salis Vehicle to prevent concurrent assignment/handover races."""
	if name:
		frappe.db.sql("SELECT name FROM `tabSalis Vehicle` WHERE name=%s FOR UPDATE", name)


def lock_driver(name):
	"""Row-lock a Salis Driver."""
	if name:
		frappe.db.sql("SELECT name FROM `tabSalis Driver` WHERE name=%s FOR UPDATE", name)


# Transport Request states keyed to their workflow docstatus, used by the
# cross-doc drive fallback so a direct state set stays consistent with the
# Transport Request Workflow.
_TR_STATE_DOCSTATUS = {
	"New": 0,
	"Validated": 0,
	"Approved": 1,
	"Scheduled": 1,
	"Fulfilled": 1,
	"Rejected": 0,
	"Cancelled": 2,
}

# Transport Request states that are terminal and must never be reopened by a
# cross-doc drive.
_TR_TERMINAL = {"Fulfilled", "Cancelled"}


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

	# 1) Prefer the native workflow transition when it is available to the user.
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
		# Fall through to the guarded direct write — never abort the parent
		# Movement transaction because the workflow path was unavailable.
		frappe.log_error(
			frappe.get_traceback(), "Salis: workflow drive fell back to direct write"
		)

	# 2) Guarded fallback: direct write consistent with the workflow docstatus map.
	values = {"status": target_state}
	if extra_fields:
		values.update(extra_fields)

	target_docstatus = _TR_STATE_DOCSTATUS.get(target_state)
	if target_docstatus is not None:
		# Keep docstatus aligned with the workflow so the document is not left in
		# an inconsistent submitted/draft state. set_value writes the column
		# directly; the workflow comment is added for an auditable trail.
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


# ---------------------------------------------------------------------------
# Rider (mandub) leave / inactive guard  — T-119
# ---------------------------------------------------------------------------
#
# Source of truth (native-first):
#   * HRMS Employee.status — the canonical employment state. Options are
#     Active / Inactive / Suspended / Left; an offboarded rider is Inactive or
#     Left (same set already used by salis/api/masar.py).
#   * HRMS Leave Application — a submitted (docstatus 1), Approved application
#     whose [from_date, to_date] covers today means the rider is on leave now.
#   * Salis Driver.status — the local deployment state (Active / Stopped /
#     On Leave / Released); anything other than Active also takes the rider out
#     of the dispatchable pool (matches salis/api/dispatch_board.py).
#
# These three are read-only signals here; this module never writes them.

#: Employee.status values that mean the person is no longer an active employee.
INACTIVE_EMPLOYEE_STATUSES = ("Inactive", "Left", "Suspended")

#: Salis Driver.status values (other than Active) that block a new delivery.
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

	# 1) Employee employment status (HRMS is the source of truth).
	if drv.employee:
		emp_status = frappe.db.get_value("Employee", drv.employee, "status")
		if emp_status in INACTIVE_EMPLOYEE_STATUSES:
			return _("Rider {0} is {1} in their Employee record and cannot receive a vehicle or fuel.").format(
				label, _(emp_status)
			)

		# 2) Approved leave covering the date.
		leave = _approved_leave_on(drv.employee, on_date)
		if leave:
			return _(
				"Rider {0} is on approved leave ({1}) covering {2} and cannot receive a vehicle or fuel."
			).format(label, leave, on_date)

	# 3) Local Salis Driver deployment status.
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
		# Leave Application DocType missing / HRMS not installed — fail open on
		# the leave check (the Employee-status and driver-status checks still run).
		return None
	return rows[0] if rows else None


def raise_rider_clearance_task(driver, vehicle=None, source_doctype=None, source_name=None):
	"""Open a clearance/settlement (تصفية) task for the Movement Supervisor to
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

	try:
		# --- Idempotency: skip if an open clearance ToDo already exists ----------
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
		# Don't re-assign a user who already has an open task for this rider.
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

		# Surface the follow-up on the triggering document's own timeline.
		if source_doctype and source_name:
			add_timeline_note(source_doctype, source_name, description)

		return created
	except Exception:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Salis: rider clearance task failed")
		return []


def _clearance_assignees(driver):
	"""Resolve the Movement Supervisor user(s) for a driver's clearance task.

	Prefers the per-record supervisor (Vehicle Assignment, then Salis Driver
	master) and falls back to the Fleet Supervisor role holders. Administrator /
	Guest and disabled users are filtered out."""
	candidates = []

	# 1) Supervisor on the driver's current (submitted, Active) Vehicle Assignment.
	assignment_sup = frappe.get_all(
		"Vehicle Assignment",
		filters={"driver": driver, "docstatus": 1, "status": "Active"},
		fields=["supervisor"],
		order_by="modified desc",
		limit=1,
	)
	if assignment_sup and assignment_sup[0].supervisor:
		candidates.append(assignment_sup[0].supervisor)

	# 2) Supervisor recorded on the Salis Driver master.
	driver_sup = frappe.db.get_value("Salis Driver", driver, "supervisor")
	if driver_sup:
		candidates.append(driver_sup)

	# 3) Fallback: every Fleet Supervisor role holder.
	if not candidates:
		candidates = frappe.get_all(
			"Has Role",
			filters={"role": "Fleet Supervisor", "parenttype": "User"},
			pluck="parent",
		)

	# De-dupe, drop system users, keep only enabled real users.
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
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Salis: timeline note failed")
