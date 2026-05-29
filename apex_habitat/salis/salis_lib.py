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
	"Fleet Regional Manager": "Regional",
	"Fleet Operations Manager": "Operations",
	"Fleet Manager": "Operations",
	"System Manager": "Operations",
	# Operations approval roles (Movement is a service provider — Operations
	# submits requests; these roles supply the DoA tier for those requests).
	"Project Manager": "Project",
	"Regional Operations Manager": "Regional",
	"Operations Manager": "Operations",
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


def log_activity(action, entity_type, entity_name, details=None):
	"""Append-only, server-written audit trail. Must never block the parent transaction."""
	try:
		payload = {
			"doctype": "Salis Activity Log",
			"action": action,
			"entity_type": entity_type,
			"entity_name": entity_name,
			"user": frappe.session.user,
			"logged_at": frappe.utils.now_datetime(),
			"details": frappe.as_json(details) if details else None,
		}
		# Logs integration: connect the event to its source record natively
		# (clickable Dynamic Link) when entity_type is a real DocType.
		if entity_type and entity_name and frappe.db.exists("DocType", entity_type):
			payload["ref_doctype"] = entity_type
			payload["ref_name"] = entity_name
		doc = frappe.get_doc(payload)
		doc.insert(ignore_permissions=True)  # audit-ok
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Salis: activity log write failed")


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
