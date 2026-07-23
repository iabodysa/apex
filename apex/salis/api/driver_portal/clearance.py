# Copyright (c) 2026, AFMCO and contributors
"""Salis Driver Portal — clearance endpoints (split from the driver_portal god module in P-180). Kernel helpers are imported from the package so the canonical dotted path apex.salis.api.driver_portal.<fn> is unchanged."""

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit

from apex.salis.api.driver_portal import (
    _resolve_driver,
    _require_enabled,
)


_CLEARANCE_FIELDS = [
	"name",
	"status",
	"clearance_reason",
	"vehicle_returned",
	"fuel_chip_returned",
	"custody_returned",
	"outstanding_fuel_exceptions",
	"outstanding_recoveries",
	"docstatus",
]


def _latest_clearance(driver):
	return frappe.db.get_value(
		"Driver Clearance",
		{"driver": driver, "docstatus": ["<", 2]},
		_CLEARANCE_FIELDS,
		as_dict=True,
		order_by="creation desc",
	)


@frappe.whitelist(allow_guest=True)
@rate_limit(key="frappe.request.remote_addr", limit=120, seconds=60)
def my_clearance():
	"""The driver's exit-clearance state and certificate availability (read).

	Identity-scoped: the driver is resolved credential-first, so this only ever
	returns the caller's own Driver Clearance. Returns the latest clearance's status,
	the blocking reason (open fuel-exception / cost-recovery counts that hold it), and
	whether the submitted clearance is issued. The separate token-authorized POST creates
	the short-lived print link only when the driver clicks download. Returns ``{"has_clearance": False}``
	(a friendly empty state, never a 403) when the driver has no clearance on record.
	This GET never creates a native Document Share Key or mutates any record."""
	_require_enabled()
	driver = _resolve_driver()
	row = _latest_clearance(driver)
	if not row:
		return {"has_clearance": False}

	# [#o19xxt]
	issued = row.get("docstatus") == 1 and row.get("status") == "Cleared"
	return {
		"has_clearance": True,
		"name": row["name"],
		"status": row.get("status"),
		"clearance_reason": row.get("clearance_reason"),
		"issued": issued,
		"blocked": row.get("status") == "Blocked",
		"vehicle_returned": bool(row.get("vehicle_returned")),
		"fuel_chip_returned": bool(row.get("fuel_chip_returned")),
		"custody_returned": bool(row.get("custody_returned")),
		"outstanding_fuel_exceptions": frappe.utils.cint(row.get("outstanding_fuel_exceptions")),
		"outstanding_recoveries": frappe.utils.cint(row.get("outstanding_recoveries")),
	}


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(key="frappe.request.remote_addr", limit=10, seconds=60)
def get_my_clearance_certificate():
	"""Issue or reuse one finite print key for the resolved driver's clearance."""
	from urllib.parse import urlencode

	_require_enabled()
	driver = _resolve_driver()
	row = _latest_clearance(driver)
	if not row or row.get("docstatus") != 1 or row.get("status") != "Cleared":
		frappe.throw(_("A cleared driver clearance is required."), frappe.PermissionError)
	row = frappe.db.get_value(
		"Driver Clearance",
		{"name": row["name"], "driver": driver},
		_CLEARANCE_FIELDS,
		as_dict=True,
		for_update=True,
	)
	if not row or row.get("docstatus") != 1 or row.get("status") != "Cleared":
		frappe.throw(_("A cleared driver clearance is required."), frappe.PermissionError)

	reference = {
		"reference_doctype": "Driver Clearance",
		"reference_docname": row["name"],
	}
	today = frappe.utils.today()
	expires_on = frappe.utils.add_days(today, 1)

	existing = frappe.get_all(
		"Document Share Key",
		filters={**reference, "expires_on": expires_on},
		fields=["key", "expires_on"],
		order_by="creation desc",
		limit=1,
	)
	if existing:
		key = existing[0]["key"]
		expires_on = existing[0]["expires_on"]
	else:
		key = frappe.get_doc("Driver Clearance", row["name"]).get_document_share_key(
			expires_on=expires_on
		)

	url = "/api/method/frappe.utils.print_format.download_pdf?" + urlencode(
		{
			"doctype": "Driver Clearance",
			"name": row["name"],
			"format": "Driver Clearance Certificate",
			"no_letterhead": 0,
			"key": key,
		}
	)
	return {
		"name": row["name"],
		"certificate_url": url,
		"expires_on": frappe.utils.cstr(expires_on),
	}
