# Shared server-side helpers for the Salis fleet module.
# Imported by Salis DocType controllers — keep side-effect free at import time.

import frappe
from frappe import _

# Ordered authority-tier ladder (ascending). A higher index means a higher
# authority. The Delegation-of-Authority gate routes each request to the tier
# its amount/quantity/scope demands, then verifies the approver actually holds
# at least that tier before allowing submit (a higher tier is required when
# scope crosses a threshold).
TIERS = ["Supervisor", "Project", "Regional", "Operations"]

# Maps the Salis operational roles onto the tier ladder. A user's effective
# authority is the highest tier among the roles they hold.
ROLE_TIER = {
	"Fleet Supervisor": "Supervisor",
	"Fleet Project Manager": "Project",
	"Fleet Manager": "Operations",
	"System Manager": "Operations",
}


def tier_rank(tier):
	"""Return the ladder index of a tier, or -1 if it is not a known tier."""
	try:
		return TIERS.index(tier)
	except (ValueError, TypeError):
		return -1


def role_tier_map():
	"""Return the effective role -> tier mapping.

	Starts from the built-in ``ROLE_TIER`` defaults and overlays any configurable
	rows from ``Salis Settings.authority_tier_map`` (a Salis Authority Tier child
	table), so the Delegation-of-Authority ladder can be extended as data without
	a code change. Configured rows win over the defaults for the same role. Only
	rows whose tier is a known ladder tier are honoured. Cached per request and
	degrades gracefully to the defaults if Settings is unavailable."""
	# Per-request memoisation: the mapping is read once per request.
	try:
		cached = frappe.local.cache.get("salis_role_tier_map")
		if cached is not None:
			return cached
	except Exception:
		cached = None

	mapping = dict(ROLE_TIER)
	try:
		rows = frappe.get_all(
			"Salis Authority Tier",
			filters={"parenttype": "Salis Settings", "parentfield": "authority_tier_map"},
			fields=["role", "tier"],
		)
		for row in rows:
			if row.get("role") and row.get("tier") in TIERS:
				mapping[row["role"]] = row["tier"]
	except Exception:
		# Settings/table not migrated yet — fall back to the built-in defaults.
		pass

	try:
		frappe.local.cache["salis_role_tier_map"] = mapping
	except Exception:
		pass
	return mapping


def user_max_tier(user):
	"""Return the highest authority tier among the user's roles, or None.

	Used by the DoA gate to compare an approver's standing against the tier a
	request requires. Considers both the built-in role mapping and any
	configurable Salis Authority Tier rows. Returns None when the user holds no
	tier-bearing role."""
	if not user:
		return None
	mapping = role_tier_map()
	best = None
	best_rank = -1
	for role in frappe.get_roles(user):
		tier = mapping.get(role)
		if tier is None:
			continue
		rank = tier_rank(tier)
		if rank > best_rank:
			best_rank = rank
			best = tier
	return best


def next_tier(tier):
	"""Return the next higher authority tier above ``tier``, or None at the top.

	None is also returned when ``tier`` is not a known tier."""
	rank = tier_rank(tier)
	if rank < 0 or rank + 1 >= len(TIERS):
		return None
	return TIERS[rank + 1]


def escalation_target(required_tier, approver):
	"""Return the tier a request must escalate to when the approver is below the
	required tier, or None when the approver already holds sufficient authority.

	The target is the required tier itself: a request needing ``required_tier``
	must be routed to someone holding at least that tier. Returns None when no
	tier is required or when the approver's standing already meets it."""
	if not required_tier:
		return None
	if tier_rank(user_max_tier(approver)) >= tier_rank(required_tier):
		return None
	return required_tier


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


def ensure_approval(reference_doctype, reference_name, required_tier=None):
	"""Block submit unless a submitted, Approved Approval Request exists for this document
	with approver != requester. Call from a controller's before_submit when a DoA gate applies.

	When ``required_tier`` is given, the gate additionally verifies that the
	request's approver holds at least that authority tier:
	an approver below the required tier cannot authorize the request, even if an
	Approved request row exists."""
	rows = frappe.get_all(
		"Approval Request",
		filters={
			"reference_doctype": reference_doctype,
			"reference_name": reference_name,
			"decision": "Approved",
			"docstatus": 1,
		},
		fields=["name", "requested_by", "approver"],
		limit=1,
	)
	if not rows:
		frappe.throw(
			_("An approved Approval Request is required before submitting {0} {1}.").format(
				reference_doctype, reference_name
			)
		)
	r = rows[0]
	if r.approver and r.requested_by and r.approver == r.requested_by:
		frappe.throw(_("Approver must differ from requester on Approval Request {0}.").format(r.name))

	if required_tier:
		approver_tier = user_max_tier(r.approver)
		if tier_rank(approver_tier) < tier_rank(required_tier):
			frappe.throw(
				_(
					"This request requires {0}-tier authority. The approver on Approval "
					"Request {1} does not hold the required tier."
				).format(required_tier, r.name)
			)
	return True
