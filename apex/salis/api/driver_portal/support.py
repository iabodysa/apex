# Copyright (c) 2026, AFMCO and contributors
"""Salis Driver Portal — support endpoints (split from the driver_portal god module in P-180). Kernel helpers are imported from the package so the canonical dotted path apex.salis.api.driver_portal.<fn> is unchanged."""

import frappe
from frappe import _

from apex.salis.api.driver_portal import (
    _resolve_driver,
    _require_enabled,
    _bound_vehicle,
    _license_countdown,
)


@frappe.whitelist()
def my_support_tickets():
	"""The current driver's support tickets, now native ERPNext Issues (read).

	Identity-scoped: the driver is resolved from the session, never client-supplied,
	so this can only return the caller's own Issues. Returns the same shape the
	portal Tickets view consumes — ``category`` (the Issue Type) and ``priority``
	mapped from the native Issue fields so the SPA needs no change."""
	_require_enabled()
	driver = _resolve_driver()
	rows = frappe.get_all(
		"Issue",
		filters={"custom_driver": driver},
		fields=[
			"name",
			"issue_type as category",
			"priority",
			"subject",
			"status",
			"creation",
		],
		order_by="creation desc",
		limit=50,
	)
	return rows



@frappe.whitelist(methods=["POST"])
def raise_support_ticket(category, priority, subject, description, attachment=None):
	"""Raise a support ticket as a native ERPNext Issue (write).

	Identity-scoped: the driver is resolved from the session, never client-supplied,
	so the Issue is always stamped with the caller's own driver (``custom_driver``)
	and email (``raised_by``). The client-supplied ``category`` maps to the Issue
	Type and ``priority`` to the Issue Priority — both seeded by
	``apex_core.setup.seeders.salis_issue_seed``. A linked Service Level
	Agreement (default for Issue) is
	applied natively by ERPNext on insert, so the response/resolution clock starts
	automatically. ``attachment`` is an optional already-uploaded File url (the SPA
	uploads the photo first) re-pointed at the new Issue. Returns ``{"name": ...}``."""
	_require_enabled()
	driver = _resolve_driver()
	project = frappe.db.get_value("Salis Driver", driver, "project")
	data = {
		"doctype": "Issue",
		"custom_driver": driver,
		"raised_by": frappe.session.user,
		"subject": subject,
		"description": description,
		"status": "Open",
	}
	# [#3u8b90]
	if category and frappe.db.exists("Issue Type", category):
		data["issue_type"] = category
	if priority and frappe.db.exists("Issue Priority", priority):
		data["priority"] = priority
	if project:
		data["project"] = project
	doc = frappe.get_doc(data)
	doc.insert(ignore_permissions=True)  # audit-ok — driver resolved server-side
	if attachment:
		_attach_file(doc.doctype, doc.name, attachment)
	return {"name": doc.name}



def _attach_file(doctype, name, file_url):
	"""Attach an already-uploaded private File to ``doctype``/``name`` (write).

	The SPA uploads the photo first (frappe.client.attach_file / upload_file), which
	creates a File row and returns its ``file_url``; this re-points that File at the
	owning record so it shows in the Issue's attachments. Best-effort: a missing/blank
	url is a silent no-op so a failed image upload never blocks the ticket itself."""
	if not file_url:
		return
	existing = frappe.db.get_value("File", {"file_url": file_url}, "name")
	if existing:
		frappe.db.set_value(
			"File", existing, {"attached_to_doctype": doctype, "attached_to_name": name}
		)



def _driver_issue(name, driver):
	"""Fetch Issue ``name`` only when it belongs to ``driver`` (custom_driver), else
	fail closed. The single scope guard shared by the ticket-detail + reply endpoints
	so one driver can never read or post to another's Issue by guessing an id."""
	issue = frappe.db.get_value(
		"Issue",
		{"name": name, "custom_driver": driver},
		[
			"name",
			"subject",
			"description",
			"status",
			"issue_type as category",
			"priority",
			"creation",
			"response_by",
			"resolution_by",
			"first_responded_on",
			"resolution_date",
		],
		as_dict=True,
	)
	if not issue:
		frappe.throw(_("Ticket not found."), frappe.DoesNotExistError)
	return issue



@frappe.whitelist()
def get_ticket(name):
	"""One support ticket's detail + its conversation (read).

	Identity-scoped: the driver is resolved from the session and the Issue is returned
	only when its ``custom_driver`` is that driver, so one driver can never open
	another's ticket. Returns the durable Issue fields plus the native SLA clock
	(``response_by``/``resolution_by`` and when each was met) and the Issue's
	Communications — the timeline the SPA's ticket detail renders. Dates are
	stringified so the JSON always serializes. Read-only, no commit."""
	_require_enabled()
	driver = _resolve_driver()
	issue = _driver_issue(name, driver)
	for f in ("creation", "response_by", "resolution_by", "first_responded_on", "resolution_date"):
		if issue.get(f):
			issue[f] = frappe.utils.cstr(issue[f])
	# [#7wn25s]
	comms = frappe.get_all(
		"Communication",
		filters={"reference_doctype": "Issue", "reference_name": name},
		fields=["name", "content", "sender", "sent_or_received", "communication_date"],
		order_by="communication_date asc",
	)
	for c in comms:
		c["communication_date"] = (
			frappe.utils.cstr(c["communication_date"]) if c.get("communication_date") else None
		)
		# [#plxvhk]
		c["content"] = frappe.utils.strip_html_tags(c.get("content") or "").strip() or None
	issue["communications"] = comms
	return issue



@frappe.whitelist(methods=["POST"])
def reply_to_ticket(name, message):
	"""Post the driver's reply to their OWN ticket as a native Communication (write).

	Identity-scoped: the Issue is resolved through ``_driver_issue`` (scoped to the
	session driver's ``custom_driver``), so a driver can only reply on their own ticket.
	Adds an ERPNext Communication threaded against the Issue (the same record type the
	desk timeline shows) and reopens a resolved/closed ticket to Open so staff see the
	new reply. Returns ``{"name": ...}`` of the new Communication. No GL."""
	_require_enabled()
	driver = _resolve_driver()
	issue = _driver_issue(name, driver)
	message = (message or "").strip()
	if not message:
		frappe.throw(_("Type a message before sending."))
	comm = frappe.get_doc(
		{
			"doctype": "Communication",
			"communication_type": "Communication",
			"sent_or_received": "Received",
			"reference_doctype": "Issue",
			"reference_name": name,
			"sender": frappe.session.user,
			"subject": _("Re: {0}").format(issue.get("subject") or name),
			"content": message,
		}
	)
	comm.insert(ignore_permissions=True)  # audit-ok — Issue resolved server-side to this driver
	# [#6v8hml]
	if issue.get("status") in ("Resolved", "Closed"):
		frappe.db.set_value("Issue", name, "status", "Open")
	return {"name": comm.name}



@frappe.whitelist(methods=["POST"])
def report_vehicle_problem(subject, description, priority=None):
	"""Raise a Vehicle Issue prefilled with the driver's bound vehicle (write).

	A thin identity-scoped wrapper over the same Issue-creation internals
	``raise_support_ticket`` uses (issue_type fixed to ``Vehicle``), stamping the
	driver's bound vehicle into the subject/description so the desk sees which vehicle
	the report is about. The driver is resolved from the session, never client-supplied.
	Returns ``{"name": ...}``. No GL."""
	_require_enabled()
	driver = _resolve_driver()
	vehicle = _bound_vehicle(driver)
	plate = frappe.db.get_value("Salis Vehicle", vehicle, "plate_number") if vehicle else None
	# [#cad16i]
	body = description or ""
	if plate or vehicle:
		body = f"{body}\n\n" + _("Vehicle: {0}").format(plate or vehicle)
	return raise_support_ticket("Vehicle", priority or "Medium", subject, body)



@frappe.whitelist(methods=["POST"])
def request_license_renewal():
	"""Raise a Compliance Issue for the driver's licence renewal (write).

	Fires only when the driver's licence is within 30 days of expiry or already
	expired (the same window the Home/Profile banner uses); otherwise refuses so the
	action can't be spammed. Reuses ``raise_support_ticket`` internals with the
	``Compliance`` issue type, so the native SLA clock starts automatically. The driver
	is resolved from the session. Returns ``{"name": ...}``. No GL."""
	_require_enabled()
	driver = _resolve_driver()
	lic = _license_countdown(driver)
	if lic.get("state") not in ("expired", "expiring"):
		frappe.throw(_("Your licence isn't due for renewal yet."))
	expiry = lic.get("expiry_date")
	subject = _("Driving licence renewal")
	body = _("Please action my driving licence renewal. Expiry on file: {0}.").format(
		expiry or _("not recorded")
	)
	return raise_support_ticket("Compliance", "High", subject, body)

