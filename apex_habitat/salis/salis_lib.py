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


def log_activity(action, entity_type, entity_name, details=None):
	"""Append-only, server-written audit trail. Must never block the parent transaction."""
	try:
		doc = frappe.get_doc(
			{
				"doctype": "Salis Activity Log",
				"action": action,
				"entity_type": entity_type,
				"entity_name": entity_name,
				"user": frappe.session.user,
				"logged_at": frappe.utils.now_datetime(),
				"details": frappe.as_json(details) if details else None,
			}
		)
		doc.insert(ignore_permissions=True)  # audit-ok
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Salis: activity log write failed")


def ensure_approval(reference_doctype, reference_name):
	"""Block submit unless a submitted, Approved Approval Request exists for this document
	with approver != requester. Call from a controller's before_submit when a DoA gate applies."""
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
	return True
