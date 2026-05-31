# Shared server-side helpers for the Salis fleet module.
# Imported by Salis DocType controllers — keep side-effect free at import time.

import frappe
from frappe import _


def lock_vehicle(name):
	"""Row-lock a Salis Vehicle to prevent concurrent assignment/handover races."""
	if name:
		frappe.db.sql("SELECT name FROM `tabSalis Vehicle` WHERE name=%s FOR UPDATE", name)


def lock_driver(name):
	"""Row-lock a Salis Driver."""
	if name:
		frappe.db.sql("SELECT name FROM `tabSalis Driver` WHERE name=%s FOR UPDATE", name)


def get_settings():
	"""Return the Salis Settings single doc."""
	return frappe.get_single("Salis Settings")


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
