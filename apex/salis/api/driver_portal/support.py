# Copyright (c) 2026, AFMCO and contributors
"""Salis Driver Portal — support endpoints (split from the driver_portal god module in P-180). Kernel helpers are imported from the package so the canonical dotted path apex.salis.api.driver_portal.<fn> is unchanged."""

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit

from apex.salis.api.driver_portal import (
    _resolve_driver,
    _require_enabled,
    _bound_vehicle,
    _license_countdown,
)


SUPPORT_SUBJECT_MAX_LENGTH = 140
SUPPORT_DESCRIPTION_MAX_LENGTH = 10_000
SUPPORT_REPLY_MAX_LENGTH = 5_000
COMMUNICATION_PAGE_DEFAULT = 20
COMMUNICATION_PAGE_MAX = 50


def _support_text(value, label, maximum):
	"""Normalize portal text and reject values beyond the endpoint boundary."""
	value = frappe.utils.cstr(value or "").strip()
	if len(value) > maximum:
		frappe.throw(
			_("{0} is too long. Use no more than {1} characters.").format(
				_(label), maximum
			)
		)
	return value


def _communication_window(offset, limit):
	offset = max(frappe.utils.cint(offset), 0)
	limit = min(
		max(frappe.utils.cint(limit) or COMMUNICATION_PAGE_DEFAULT, 1),
		COMMUNICATION_PAGE_MAX,
	)
	return offset, limit


def _driver_identity(driver):
	"""Return a stored user email or a stable driver-derived audit identity."""
	driver_user = frappe.db.get_value("Salis Driver", driver, "driver_user")
	if driver_user and driver_user != "Guest":
		return driver_user
	local_part = frappe.scrub(driver).replace("_", "-")
	return f"{local_part}@driver.invalid"


@frappe.whitelist(allow_guest=True)
@rate_limit(limit=120, seconds=60)
def my_support_tickets():
	"""The current driver's support tickets, now native ERPNext Issues (read).

	Identity-scoped: the driver is resolved credential-first, never client-supplied,
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



@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=10, seconds=60)
def raise_support_ticket(
	category,
	priority,
	subject,
	description,
	photo=None,
	photo_filename=None,
):
	"""Raise a support ticket as a native ERPNext Issue (write).

	Identity-scoped: the driver is resolved credential-first, never client-supplied,
	so the Issue is always stamped with the caller's own driver (``custom_driver``)
	and email (``raised_by``). The client-supplied ``category`` maps to the Issue
	Type and ``priority`` to the Issue Priority — both seeded by
	``apex_core.setup.seeders.salis_issue_seed``. A linked Service Level
	Agreement (default for Issue) is
	applied natively by ERPNext on insert, so the response/resolution clock starts
	automatically. An optional image is validated and saved as a private native File
	directly on this newly created Issue; caller-supplied File URLs are not accepted.
	Returns ``{"name": ...}``."""
	_require_enabled()
	driver = _resolve_driver()
	return _create_support_ticket(
		driver,
		category,
		priority,
		subject,
		description,
		photo,
		photo_filename,
	)


def _create_support_ticket(
	driver,
	category,
	priority,
	subject,
	description,
	photo=None,
	photo_filename=None,
):
	"""Create one Issue after the public endpoint resolves its driver authority."""
	subject = _support_text(subject, "Subject", SUPPORT_SUBJECT_MAX_LENGTH)
	description = _support_text(
		description,
		"Description",
		SUPPORT_DESCRIPTION_MAX_LENGTH,
	)
	driver_identity = _driver_identity(driver)
	project = frappe.db.get_value("Salis Driver", driver, "project")
	data = {
		"doctype": "Issue",
		"custom_driver": driver,
		"raised_by": driver_identity,
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
	from apex.salis.api.driver_portal.images import save_driver_image

	save_driver_image(photo, photo_filename, doc.doctype, doc.name)
	return {"name": doc.name}



def _driver_issue(name, driver):
	"""Fetch Issue ``name`` only when it belongs to ``driver`` (custom_driver), else
	fail closed. The single scope guard shared by the ticket-detail + reply endpoints
	so one driver can never read or post to another's Issue by guessing an id."""
	fields = [
		"name",
		"subject",
		"description",
		"status",
		"issue_type as category",
		"priority",
		"creation",
	]
	optional_sla_fields = (
		"response_by",
		"resolution_by",
		"first_responded_on",
		"resolution_date",
	)
	meta = frappe.get_meta("Issue")
	fields.extend(field for field in optional_sla_fields if meta.has_field(field))
	issue = frappe.db.get_value(
		"Issue",
		{"name": name, "custom_driver": driver},
		fields,
		as_dict=True,
	)
	if not issue:
		frappe.throw(_("Ticket not found."), frappe.DoesNotExistError)
	for fieldname in optional_sla_fields:
		issue.setdefault(fieldname, None)
	return issue



@frappe.whitelist(allow_guest=True)
@rate_limit(limit=120, seconds=60)
def get_ticket(name, communication_offset=0, communication_limit=COMMUNICATION_PAGE_DEFAULT):
	"""One support ticket's detail + its conversation (read).

	Identity-scoped: the driver is resolved credential-first and the Issue is returned
	only when its ``custom_driver`` is that driver, so one driver can never open
	another's ticket. Returns the durable Issue fields plus the native SLA clock
	(``response_by``/``resolution_by`` and when each was met) and the Issue's
	Communications — the timeline the SPA's ticket detail renders. The conversation
	is returned in deterministic bounded pages using ``communication_offset`` and
	``communication_limit`` plus ``communication_has_more``. Dates are stringified
	so the JSON always serializes. Read-only, no commit."""
	_require_enabled()
	driver = _resolve_driver()
	issue = _driver_issue(name, driver)
	for f in ("creation", "response_by", "resolution_by", "first_responded_on", "resolution_date"):
		if issue.get(f):
			issue[f] = frappe.utils.cstr(issue[f])
	# [#7wn25s]
	communication_offset, communication_limit = _communication_window(
		communication_offset,
		communication_limit,
	)
	comms = frappe.get_all(
		"Communication",
		filters={"reference_doctype": "Issue", "reference_name": name},
		fields=[
			"name",
			"content",
			"sender",
			"sent_or_received",
			"communication_date",
			"creation",
		],
		order_by="communication_date asc, creation asc, name asc",
		limit_start=communication_offset,
		limit=communication_limit + 1,
	)
	has_more = len(comms) > communication_limit
	comms = comms[:communication_limit]
	for c in comms:
		c["communication_date"] = (
			frappe.utils.cstr(c["communication_date"]) if c.get("communication_date") else None
		)
		c["creation"] = frappe.utils.cstr(c["creation"]) if c.get("creation") else None
		# [#plxvhk]
		c["content"] = frappe.utils.strip_html_tags(c.get("content") or "").strip() or None
	issue["communications"] = comms
	issue["communication_has_more"] = has_more
	issue["communication_next_offset"] = (
		communication_offset + len(comms) if has_more else None
	)
	return issue



@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=10, seconds=60)
def reply_to_ticket(name, message):
	"""Post the driver's reply to their OWN ticket as a native Communication (write).

	Identity-scoped: the Issue is resolved through ``_driver_issue`` (scoped to the
	credential-resolved driver's ``custom_driver``), so a driver can only reply on their own ticket.
	Adds an ERPNext Communication threaded against the Issue (the same record type the
	desk timeline shows) and reopens a resolved/closed ticket to Open so staff see the
	new reply. Returns ``{"name": ...}`` of the new Communication. No GL."""
	_require_enabled()
	driver = _resolve_driver()
	driver_identity = _driver_identity(driver)
	issue = _driver_issue(name, driver)
	message = (message or "").strip()
	if not message:
		frappe.throw(_("Type a message before sending."))
	message = _support_text(message, "Reply", SUPPORT_REPLY_MAX_LENGTH)
	comm = frappe.get_doc(
		{
			"doctype": "Communication",
			"communication_type": "Communication",
			"sent_or_received": "Received",
			"reference_doctype": "Issue",
			"reference_name": name,
			"sender": driver_identity,
			"subject": _("Re: {0}").format(issue.get("subject") or name),
			"content": message,
		}
	)
	comm.insert(ignore_permissions=True)  # audit-ok — Issue resolved server-side to this driver
	# [#6v8hml]
	if issue.get("status") in ("Resolved", "Closed"):
		frappe.db.set_value("Issue", name, "status", "Open")
	return {"name": comm.name}



@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=10, seconds=60)
def report_vehicle_problem(subject, description, priority=None):
	"""Raise a Vehicle Issue prefilled with the driver's bound vehicle (write).

	A thin identity-scoped wrapper over the same Issue-creation internals
	``raise_support_ticket`` uses (issue_type fixed to ``Vehicle``), stamping the
	driver's bound vehicle into the subject/description so the desk sees which vehicle
	the report is about. The driver is resolved credential-first, never client-supplied.
	Returns ``{"name": ...}``. No GL."""
	_require_enabled()
	driver = _resolve_driver()
	vehicle = _bound_vehicle(driver)
	plate = frappe.db.get_value("Salis Vehicle", vehicle, "plate_number") if vehicle else None
	# [#cad16i]
	body = description or ""
	if plate or vehicle:
		body = f"{body}\n\n" + _("Vehicle: {0}").format(plate or vehicle)
	return _create_support_ticket(
		driver,
		"Vehicle",
		priority or "Medium",
		subject,
		body,
	)



@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=10, seconds=60)
def request_license_renewal():
	"""Raise a Compliance Issue for the driver's licence renewal (write).

	Fires only when the driver's licence is within 30 days of expiry or already
	expired (the same window the Home/Profile banner uses); otherwise refuses so the
	action can't be spammed. Reuses ``raise_support_ticket`` internals with the
	``Compliance`` issue type, so the native SLA clock starts automatically. The driver
	is resolved credential-first. Returns ``{"name": ...}``. No GL."""
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
	return _create_support_ticket(
		driver,
		"Compliance",
		"High",
		subject,
		body,
	)
