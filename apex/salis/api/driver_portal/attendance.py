# Copyright (c) 2026, AFMCO and contributors
"""Salis Driver Portal — attendance endpoints (split from the driver_portal god module in P-180). Kernel helpers are imported from the package so the canonical dotted path apex.salis.api.driver_portal.<fn> is unchanged."""

import frappe
from frappe import _

from apex.salis.api.driver_portal import (
    _resolve_driver,
    _require_enabled,
    _today_attendance_state,
)


def _attendance_state(doc):
	"""Project a Driver Attendance doc to the portal's state shape.

	The single source of truth for what the SPA shows — identical in shape to
	``get_today_attendance``'s return — so a check-in/out response updates the page
	reactively without a reload. Time fields are stringified for JSON."""
	check_in = frappe.utils.cstr(doc.check_in) if doc.check_in else None
	check_out = frappe.utils.cstr(doc.check_out) if doc.check_out else None
	return {
		"name": doc.name,
		"exists": True,
		"checked_in": bool(check_in),
		"checked_out": bool(check_out),
		"status": doc.status,
		"check_in": check_in,
		"check_out": check_out,
		"worked_hours": doc.worked_hours,
	}



def _today_attendance(driver):
	name = frappe.db.get_value(
		"Driver Attendance",
		{"driver": driver, "attendance_date": frappe.utils.today(), "docstatus": ["<", 2]},
		"name",
	)
	if name:
		return frappe.get_doc("Driver Attendance", name)
	return frappe.get_doc(
		{"doctype": "Driver Attendance", "driver": driver,
		 "attendance_date": frappe.utils.today(), "status": "Present"}
	)



@frappe.whitelist()
def get_today_attendance():
	"""Today's attendance state for the current driver (read).

	Identity-scoped: the driver is resolved from the session, never client-supplied,
	so this can only ever return the caller's own record. Read-only, no commit.
	The payload shape and flags are documented on ``_today_attendance_state``."""
	_require_enabled()
	driver = _resolve_driver()
	return _today_attendance_state(driver)



def _month_bounds(month=None):
	"""(first_day, last_day) for ``month`` (``YYYY-MM``), defaulting to this month.

	An unparseable/blank value falls back to the current month rather than raising,
	so a malformed client param never 500s the history view."""
	anchor = frappe.utils.getdate()
	if month:
		try:
			anchor = frappe.utils.getdate(f"{month}-01")
		except Exception:
			pass
	return frappe.utils.get_first_day(anchor), frappe.utils.get_last_day(anchor)



@frappe.whitelist()
def my_attendance(month=None):
	"""The current driver's OWN attendance rows for a month (read).

	Identity-scoped: the driver is resolved from the session, never client-supplied,
	so this can only ever return the caller's own records — it cannot read another
	driver's history. ``month`` is ``YYYY-MM`` and defaults to the current month.

	Returns ``{"month", "rows"}`` where each row carries the date, status, and the
	stringified check-in/out times (newest day first) — the same display vocabulary
	the today card uses, so the SPA renders the month strip with no extra mapping.
	Read-only, no commit."""
	_require_enabled()
	driver = _resolve_driver()
	start, end = _month_bounds(month)
	rows = frappe.get_all(
		"Driver Attendance",
		filters={
			"driver": driver,
			"attendance_date": ["between", [start, end]],
			"docstatus": ["<", 2],
		},
		fields=["name", "attendance_date", "status", "check_in", "check_out", "worked_hours"],
		order_by="attendance_date desc",
	)
	for r in rows:
		r["attendance_date"] = frappe.utils.cstr(r["attendance_date"])
		r["check_in"] = frappe.utils.cstr(r["check_in"]) if r.get("check_in") else None
		r["check_out"] = frappe.utils.cstr(r["check_out"]) if r.get("check_out") else None
	return {"month": frappe.utils.cstr(start)[:7], "rows": rows}



def _persist_attendance(doc):
	"""Persist a get-or-created Driver Attendance as a SUBMITTED presence record.

	A portal check-in/out is authoritative, so the record must reach docstatus 1 —
	that is what ``missing_attendance_watch`` and the Supervisor-Delay reconciler key
	on (``docstatus = 1``). A draft would leave a compliant portal user tripping a
	daily "Supervisor Delay" alert that never auto-resolves.

	The write is server-authoritative (the driver was resolved from the session
	identity, never client-supplied), so a single ``ignore_permissions`` flag is set
	on the doc and the create/submit/update all run under it — one guarded operation,
	matching the endpoint's prior single guarded write.

	* A new (or still-draft) record is inserted then submitted.
	* An already-submitted record (a second tap the same day — e.g. check-in then
	  check-out) is updated in place; ``check_out`` / ``worked_hours`` / ``images``
	  are ``allow_on_submit`` on the DocType, so ``save`` persists them with no
	  amendment.
	"""
	doc.flags.ignore_permissions = True  # audit-ok — driver resolved from session identity
	if doc.docstatus == 0:
		doc.insert()
		doc.submit()
	else:
		doc.save()



@frappe.whitelist(methods=["POST"])
def driver_check_in(photo=None):
	"""Record the driver's presence for today and SUBMIT it.

	A portal check-in is an authoritative record of presence, so the Driver
	Attendance is submitted (docstatus 1) — not left in draft. This is what the
	rest of the module treats as "attendance recorded": ``missing_attendance_watch``
	and the Supervisor-Delay branch of ``reconcile_operations_alerts`` both key on
	``docstatus = 1``. Leaving the record in draft meant a portal-using driver still
	tripped a daily "Supervisor Delay" alert that never auto-resolved. Submitting on
	check-in satisfies the watcher, so a compliant driver raises no alert (and any
	already-open one auto-resolves on the next reconcile pass).

	The Driver role holds a ``submit`` DocPerm on Driver Attendance (if_owner via the
	identity-scoped resolution here); ``ignore_permissions`` keeps the write
	server-authoritative regardless.
	"""
	_require_enabled()
	driver = _resolve_driver()
	doc = _today_attendance(driver)
	doc.check_in = frappe.utils.nowtime()
	# [#t537co] Check-in opens the shift; it must NEVER stamp check-out. Frappe core
	# fills EVERY Time field with nowtime() on a brand-new doc (create_new.py
	# set_dynamic_default_values, NOT gated on a field default), and insert()'s
	# _set_defaults() copies that phantom onto our row via update_if_missing — so a
	# bare check-in would persist check_out == check_in (an instant zero-length
	# "full day"). Excluding check_out/worked_hours from update_if_missing keeps the
	# phantom out; check-out is a separate, later action.
	doc.check_out = None
	doc.worked_hours = 0
	for _field in ("check_out", "worked_hours"):
		if _field not in doc.dont_update_if_missing:
			doc.dont_update_if_missing.append(_field)
	if not doc.status:
		doc.status = "Present"
	if photo:
		doc.append("images", {"image": photo, "captured_at": frappe.utils.now_datetime()})
	_persist_attendance(doc)
	return _attendance_state(doc)



@frappe.whitelist(methods=["POST"])
def driver_check_out(photo=None):
	"""Stamp check-out on today's attendance.

	Check-in already submitted the record, so check-out updates a submitted Driver
	Attendance — ``check_out``, ``worked_hours`` and the ``images`` table are
	``allow_on_submit`` on the DocType, so ``save`` persists them without an
	amendment. If a driver checks out without ever checking in (no record yet), the
	get-or-create returns a fresh draft, which is inserted and submitted here so the
	day still counts as recorded presence.
	"""
	_require_enabled()
	driver = _resolve_driver()
	doc = _today_attendance(driver)
	now = frappe.utils.nowtime()
	# [#t537zero] Refuse a zero-length (or negative) day: a check-out at or before the
	# existing check-in would record check_out == check_in (worked_hours 0). Surface a
	# friendly message instead of silently stamping an instant "full day".
	if doc.check_in and not _is_after(doc.attendance_date, doc.check_in, now):
		frappe.throw(
			_("You can't check out at or before your check-in time. Try again in a moment.")
		)
	# [#t537co] If the driver checks out without ever checking in, the get-or-created
	# row has no check-in; keep it that way. Frappe core phantom-fills every Time
	# field with nowtime() at insert (see driver_check_in), which would otherwise
	# fabricate a check_in == check_out (instant zero-length day). Record presence as
	# a check-out only.
	if not doc.check_in:
		doc.check_in = None
		if "check_in" not in doc.dont_update_if_missing:
			doc.dont_update_if_missing.append("check_in")
	doc.check_out = now
	if not doc.status:
		doc.status = "Present"
	if photo:
		doc.append("images", {"image": photo, "captured_at": frappe.utils.now_datetime()})
	_persist_attendance(doc)
	return _attendance_state(doc)



def _is_after(attendance_date, earlier_time, later_time):
	"""True when ``later_time`` is strictly after ``earlier_time`` (both Frappe Time
	values on the same ``attendance_date``). Used to reject a zero-length shift."""
	earlier = frappe.utils.get_datetime(f"{attendance_date} {earlier_time}")
	later = frappe.utils.get_datetime(f"{attendance_date} {later_time}")
	return frappe.utils.time_diff_in_seconds(later, earlier) > 0

