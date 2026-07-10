# Copyright (c) 2026, AFMCO and contributors
"""Salis Driver Portal — clearance endpoints (split from the driver_portal god module in P-180). Kernel helpers are imported from the package so the canonical dotted path apex.salis.api.driver_portal.<fn> is unchanged."""

import frappe

from apex.salis.api.driver_portal import (
    _resolve_driver,
    _require_enabled,
)


@frappe.whitelist()
def my_clearance():
	"""The driver's exit-clearance state + certificate link when issued (read).

	Identity-scoped: the driver is resolved from the session, so this only ever
	returns the caller's own Driver Clearance. Returns the latest clearance's status,
	the blocking reason (open fuel-exception / cost-recovery counts that hold it), and
	— once the clearance is submitted (Cleared) — the print URL for the Driver Clearance
	Certificate so the driver can download the PDF. Returns ``{"has_clearance": False}``
	(a friendly empty state, never a 403) when the driver has no clearance on record.
	Read-only, no commit."""
	_require_enabled()
	driver = _resolve_driver()
	row = frappe.db.get_value(
		"Driver Clearance",
		{"driver": driver, "docstatus": ["<", 2]},
		[
			"name",
			"status",
			"clearance_reason",
			"vehicle_returned",
			"fuel_chip_returned",
			"custody_returned",
			"outstanding_fuel_exceptions",
			"outstanding_recoveries",
			"docstatus",
		],
		as_dict=True,
		order_by="creation desc",
	)
	if not row:
		return {"has_clearance": False}

	# A submitted, Cleared clearance is the issued state — expose the certificate PDF.
	issued = row.get("docstatus") == 1 and row.get("status") == "Cleared"
	certificate_url = None
	if issued:
		# Canonical download-pdf URL for the standard certificate print format.
		from urllib.parse import urlencode

		certificate_url = "/api/method/frappe.utils.print_format.download_pdf?" + urlencode(
			{
				"doctype": "Driver Clearance",
				"name": row["name"],
				"format": "Driver Clearance Certificate",
				"no_letterhead": 0,
			}
		)
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
		"certificate_url": certificate_url,
	}

