# Copyright (c) 2026, AFMCO and contributors
"""Salis Driver Portal — profile endpoints (split from the driver_portal god module in P-180). Kernel helpers are imported from the package so the canonical dotted path apex.salis.api.driver_portal.<fn> is unchanged."""

import frappe

from apex.salis.api.driver_portal import (
    _portal_enabled,
    _license_warn_days,
    _find_driver,
    _resolve_driver,
    _require_enabled,
    _is_staff,
    _staff_links,
    _user_full_name,
    _vehicle_last_site_maps_url,
)


def _fmt_date(value):
	return frappe.utils.cstr(value) if value else None



def _days_until(value):
	"""Whole days from today until ``value``, or None — mirrors masar's helper so
	a missing/unparseable expiry never raises."""
	if not value:
		return None
	try:
		return frappe.utils.date_diff(value, frappe.utils.today())
	except Exception:
		return None



def _employee_documents(employee):
	"""The linked Employee's Iqama/passport identity expiries, read defensively.

	Mirrors ``masar.get_worker_context``: Employee field names vary across HR setups,
	so every field is read via ``.get()`` on the cached doc and a missing field
	surfaces as None rather than erroring. Returns a list of ``{type, number, expiry,
	days_left}`` entries (only for documents on file), the same shape the Masar
	profile consumes — so the SPA reuses one renderer. Read-only."""
	if not employee or not frappe.db.exists("Employee", employee):
		return []
	emp = frappe.get_cached_doc("Employee", employee)
	documents = []
	# Same Iqama field fallbacks masar uses (iqama/iqama_no, iqama_expiry/valid_upto).
	iqama_no = emp.get("iqama") or emp.get("iqama_no")
	iqama_expiry = emp.get("iqama_expiry") or emp.get("valid_upto")
	if iqama_no or iqama_expiry:
		documents.append(
			{
				"type": "iqama",
				"number": iqama_no,
				"expiry": _fmt_date(iqama_expiry),
				"days_left": _days_until(iqama_expiry),
			}
		)
	# Passport mirrors masar — surfaced only when a number is on file.
	passport_no = emp.get("passport_number")
	if passport_no:
		documents.append(
			{
				"type": "passport",
				"number": passport_no,
				"expiry": _fmt_date(emp.get("passport_expiry")),
				"days_left": _days_until(emp.get("passport_expiry")),
			}
		)
	return documents



def _project_label(code):
	"""Resolve a Project link id (e.g. ``PROJ-0038``) to its display name.

	The portal shows the project's human ``project_name`` (the Project DocType's
	title field), not the autonamed series code. Returns the resolved name, or the
	code itself as a fallback when the link is blank or cannot be resolved — so a
	missing/renamed project never blanks the field. Read-only."""
	if not code:
		return code
	return frappe.db.get_value("Project", code, "project_name") or code



@frappe.whitelist()
def get_driver_context():
	"""Portal bootstrap (read): enabled flag, whether the user is linked to a
	driver, and the driver profile. Never raises for an unlinked user.

	For an UNLINKED user the payload is still useful (not a dead-end): it carries
	``is_staff`` (does the user hold a Salis desk role), the user's ``full_name``,
	and ``links`` — a permission-filtered set of desk destinations. The SPA renders
	a friendly staff panel or a generic explainer from these fields instead of a
	bare error. Action endpoints remain strictly driver-scoped (unchanged)."""
	user = frappe.session.user
	if not _portal_enabled():
		# [#p6q8jd]
		staff = _is_staff(user)
		return {
			"enabled": False,
			"linked": False,
			"driver": None,
			"is_staff": staff,
			"full_name": _user_full_name(user),
			"links": _staff_links(user) if staff else [],
		}
	driver = _find_driver()
	if not driver:
		staff = _is_staff(user)
		return {
			"enabled": True,
			"linked": False,
			"driver": None,
			"is_staff": staff,
			"full_name": _user_full_name(user),
			"links": _staff_links(user) if staff else [],
		}
	d = frappe.db.get_value(
		"Salis Driver", driver,
		["name", "full_name", "status", "current_vehicle", "license_expiry"],
		as_dict=True,
	)
	# [#1grmf3]
	if d and d.get("license_expiry"):
		d["license_expiry"] = frappe.utils.cstr(d["license_expiry"])
	return {"enabled": True, "linked": True, "driver": d}



@frappe.whitelist()
def get_driver_profile():
	"""The current driver's OWN profile (read).

	Identity-scoped: the driver is resolved from the session, never client-supplied,
	so this can only ever return the caller's own record — it cannot leak another
	driver's data. Read-only, no commit. Returns the durable fields the portal
	profile view shows (name, employee, status, license, contact, current vehicle).
	Date fields are stringified so the JSON response always serializes."""
	_require_enabled()
	driver = _resolve_driver()
	d = frappe.db.get_value(
		"Salis Driver", driver,
		["name", "full_name", "employee", "status", "phone", "project",
		 "license_number", "license_expiry", "current_vehicle"],
		as_dict=True,
	) or {}
	if d.get("license_expiry"):
		d["license_expiry"] = frappe.utils.cstr(d["license_expiry"])
	# [#projlbl] portal shows the project's display name, not its series code
	if d.get("project"):
		d["project"] = _project_label(d["project"])
	# Iqama/passport expiries from the linked Employee (defensive .get(), like masar)
	d["documents"] = _employee_documents(d.get("employee"))
	return d



# [#vehcmp] Compliance child rows the driver actually cares about, in the order
# they should read on the card. "Operating Card"/"Other" are deliberately omitted —
# a driver acts on the registration (istimara), insurance, and periodic inspection
# (fahes) expiries; the rest is back-office. Keys are the stable Select option
# values on Salis Vehicle Compliance.compliance_type.
_DRIVER_COMPLIANCE_TYPES = (
	"Registration (Istimara)",
	"Insurance",
	"Periodic Inspection",
)



def _vehicle_compliance(vehicle):
	"""The driver-relevant compliance documents for a vehicle (read).

	Reads the ``compliance_documents`` child table and returns one entry per
	driver-relevant document type (registration/insurance/inspection) that has an
	expiry date, newest-expiring first within each type kept. Each entry carries:

	* ``compliance_type``  — stable English Select value (client maps to a label)
	* ``document_number``  — may be blank
	* ``expiry_date``      — ISO string (stringified so JSON serializes)
	* ``days_to_expiry``   — signed int; negative = already expired
	* ``state``            — ``expired`` | ``expiring`` (<= 30 days) | ``valid``

	The amber/red threshold (``expiring`` at <= 30 days) is computed server-side so
	the SPA needs no date math and both portal languages render identically. Returns
	an empty list when the vehicle tracks no documents — the page omits the section.
	"""
	rows = frappe.get_all(
		"Salis Vehicle Compliance",
		filters={"parent": vehicle, "parenttype": "Salis Vehicle"},
		fields=["compliance_type", "document_number", "expiry_date"],
		order_by="expiry_date asc",
	)
	today = frappe.utils.getdate()
	warn_days = _license_warn_days()
	out = []
	for r in rows:
		if r.get("compliance_type") not in _DRIVER_COMPLIANCE_TYPES or not r.get("expiry_date"):
			continue
		days = frappe.utils.date_diff(r["expiry_date"], today)
		out.append(
			{
				"compliance_type": r["compliance_type"],
				"document_number": r.get("document_number") or None,
				"expiry_date": frappe.utils.cstr(r["expiry_date"]),
				"days_to_expiry": days,
				"state": "expired" if days < 0 else ("expiring" if days <= warn_days else "valid"),
			}
		)
	return out



@frappe.whitelist()
def get_my_vehicle():
	"""The current driver's CURRENT vehicle, enriched for the driver view (read).

	Identity-scoped: resolves the driver from the session, then returns the vehicle
	bound to them — their ``current_vehicle`` if set, otherwise the vehicle on an
	Active Vehicle Assignment (the same binding rule ``_vehicle_bound_to_driver``
	enforces for writes). Returns ``{"vehicle": None}`` (a friendly empty state) when
	no vehicle is bound. Read-only, no commit.

	The payload carries the fields a DRIVER acts on — plate, category, status,
	odometer, planned fuel grade, the assignment start, the resolved project name,
	and a ``compliance`` list (registration/insurance/inspection expiries with a
	server-computed near-/over-expiry ``state``; see ``_vehicle_compliance``).
	``compliance_status`` is the vehicle's rolled-up flag. Ownership (Owned/Rented)
	is intentionally NOT surfaced: it is a back-office attribute with no meaning to a
	driver. Empty fields are returned as null/[] so the SPA omits them cleanly.
	"""
	_require_enabled()
	driver = _resolve_driver()

	vehicle = frappe.db.get_value("Salis Driver", driver, "current_vehicle")
	assignment = None
	if not vehicle:
		# [#n00nxa]
		assignment = frappe.db.get_value(
			"Vehicle Assignment",
			{"driver": driver, "status": "Active"},
			["name", "vehicle", "start_date"],
			as_dict=True,
		)
		if assignment:
			vehicle = assignment.get("vehicle")

	if not vehicle:
		return {"vehicle": None}

	v = frappe.db.get_value(
		"Salis Vehicle", vehicle,
		["name", "plate_number", "vehicle_category", "status", "odometer",
		 "planned_fuel_grade", "compliance_status", "project"],
		as_dict=True,
	) or {}

	# [#projlbl] portal shows the project's display name, not its series code
	if v.get("project"):
		v["project"] = _project_label(v["project"])

	# [#vehcmp] driver-relevant expiries with a server-computed warning state
	v["compliance"] = _vehicle_compliance(vehicle)

	# [#kcrj1g]
	if assignment is None:
		assignment = frappe.db.get_value(
			"Vehicle Assignment",
			{"driver": driver, "vehicle": vehicle, "status": "Active"},
			["name", "start_date"],
			as_dict=True,
		)
	v["assignment_start"] = (
		frappe.utils.cstr(assignment["start_date"])
		if assignment and assignment.get("start_date")
		else None
	)
	# [#vehmap] last-known site deep-link (derived from the latest trip route — no GPS field)
	v["last_site_maps_url"] = _vehicle_last_site_maps_url(vehicle)
	return {"vehicle": v}

