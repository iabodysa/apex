"""Salis Driver Portal — identity-scoped, no-financial-impact APIs for the mobile
SPA at /driver. Every endpoint resolves the CURRENT user to a Salis Driver and acts
only on that driver's records; the client never supplies the driver id."""

import frappe
from frappe import _

# [#g14lmr]
STAFF_ROLES = (
	"Fleet Manager",
	"Fleet Project Manager",
	"Fleet Supervisor",
	"Finance Manager",
	"System Manager",
)


def _portal_enabled():
	return bool(frappe.db.get_single_value("Salis Settings", "enable_driver_portal"))


def _find_driver(user=None):
	"""Return the Salis Driver name linked to the session user, or None.

	Soft lookup with no exception — used by the portal bootstrap so an
	unlinked user (e.g. an admin previewing the page) gets a friendly screen
	instead of a 403 and an uncaught client error."""
	user = user or frappe.session.user
	employee = frappe.db.get_value("Employee", {"user_id": user}, "name")
	if not employee:
		return None
	return frappe.db.get_value("Salis Driver", {"employee": employee}, "name")


def _resolve_driver(user=None):
	"""Return the Salis Driver name linked to the session user, else 403.

	Used by every action endpoint so writes are always scoped to a real,
	server-resolved driver."""
	driver = _find_driver(user)
	if not driver:
		frappe.throw(_("No Salis Driver is linked to your account."), frappe.PermissionError)
	return driver


def _require_enabled():
	if not _portal_enabled():
		frappe.throw(_("Driver portal is not enabled."), frappe.PermissionError)


def _is_staff(user=None):
	"""True when the user holds any Salis desk/oversight role (display hint)."""
	user = user or frappe.session.user
	if user == "Administrator":
		return True
	return bool(set(frappe.get_roles(user)) & set(STAFF_ROLES))


def _staff_links(user=None):
	"""Useful desk destinations for an unlinked staff user, filtered to what
	they may actually open. Each entry carries an English label and an /app URL;
	links are included only when the user holds a required role or has read
	permission on the underlying DocType. The mobile portal action endpoints stay
	driver-scoped — these are navigation hints to the full desk, nothing more."""
	user = user or frappe.session.user
	roles = set(frappe.get_roles(user))
	links = []

	# [#9qndfi]
	if user == "Administrator" or roles & set(STAFF_ROLES):
		links.append({"label": "Salis Workspace", "url": "/app/salis"})

	# [#8ubj1y]
	dispatch_roles = {"System Manager", "Fleet Manager", "Fleet Project Manager", "Fleet Supervisor"}
	if user == "Administrator" or roles & dispatch_roles:
		links.append({"label": "Dispatch Board", "url": "/app/salis-dispatch-board"})

	# [#cd8prs]
	if frappe.has_permission("Transport Request", "read", user=user):
		links.append({"label": "Transport Requests", "url": "/app/transport-request"})

	# [#mpoxzg]
	fuel_roles = {"System Manager", "Fleet Manager", "Fleet Project Manager", "Finance Manager"}
	if user == "Administrator" or roles & fuel_roles:
		links.append({"label": "Fuel Approval Console", "url": "/app/fuel-approval-console"})

	return links


def _user_full_name(user=None):
	user = user or frappe.session.user
	return frappe.utils.get_fullname(user) or user


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
				"state": "expired" if days < 0 else ("expiring" if days <= 30 else "valid"),
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


@frappe.whitelist()
def my_trips_today():
	"""Today's Dispatch Trips for the current driver (read)."""
	_require_enabled()
	driver = _resolve_driver()
	trips = frappe.get_all(
		"Dispatch Trip",
		filters={"driver": driver, "trip_date": frappe.utils.today()},
		fields=["name", "route_plan", "vehicle", "depart_time", "return_time", "status"],
		order_by="depart_time asc",
	)
	_attach_trip_maps(trips)  # one-tap Maps before _label_trips overwrites route_plan
	_label_trips(trips)  # cards show plate / route name, not raw link ids
	_attach_trip_log_state(trips, driver)  # cards show started/completed without a second call
	return trips


@frappe.whitelist()
def my_trips_recent(days=30, limit=50):
	"""The current driver's recent Dispatch Trips, newest first (read).

	Identity-scoped via endpoint-scoped ``get_all`` (the ``my_trips_today``
	precedent): the driver is resolved from the session and every row is filtered on
	that driver, so this can only return the caller's own trips. Backs the Trips
	view's "recent/past" tab while ``my_trips_today`` stays the default — the SPA
	switches endpoints, the card shape is identical (route/vehicle link ids swapped
	for human labels by the same ``_label_trips``).

	``days`` bounds the window (trip_date >= today - days; defaults to 30) and
	``limit`` caps the rows, so the list never grows unbounded for a long-tenured
	driver. ``trip_date`` is included (and stringified) so the SPA can group/sort by
	day. Read-only, no commit."""
	_require_enabled()
	driver = _resolve_driver()
	since = frappe.utils.add_days(frappe.utils.today(), -(frappe.utils.cint(days) or 30))
	trips = frappe.get_all(
		"Dispatch Trip",
		filters={"driver": driver, "trip_date": [">=", since]},
		fields=["name", "trip_date", "route_plan", "vehicle", "depart_time", "return_time", "status"],
		order_by="trip_date desc, depart_time desc",
		limit=frappe.utils.cint(limit) or 50,
	)
	_attach_trip_maps(trips)  # one-tap Maps before _label_trips overwrites route_plan
	_label_trips(trips)  # cards show plate / route name, not raw link ids
	for t in trips:
		t["trip_date"] = frappe.utils.cstr(t["trip_date"]) if t.get("trip_date") else None
	return trips


def _label_trips(trips):
	"""Swap route_plan / vehicle link ids for their human labels (Route Plan.
	route_name, Salis Vehicle.plate_number) so the driver's cards read names."""

	def labels(doctype, names, field):
		if not names:
			return {}
		rows = frappe.get_all(
			doctype, filters={"name": ["in", list(names)]}, fields=["name", field]
		)
		return {r["name"]: r[field] for r in rows}

	plates = labels(
		"Salis Vehicle", {t.get("vehicle") for t in trips if t.get("vehicle")}, "plate_number"
	)
	routes = labels(
		"Route Plan", {t.get("route_plan") for t in trips if t.get("route_plan")}, "route_name"
	)
	for t in trips:
		if t.get("vehicle"):
			t["vehicle"] = plates.get(t["vehicle"], t["vehicle"])
		if t.get("route_plan"):
			t["route_plan"] = routes.get(t["route_plan"], t["route_plan"])


def _route_first_stop_maps_url(route_plan):
	"""The Google Maps deep-link for a route plan's first mapped stop, or None.

	Reuses masar's read-only ``_ordered_stops`` so the URL is the exact one the
	Route screen already renders. Returns the first stop pickup that carries a
	``google_maps_url`` (the trip's first navigable destination), so a Trips/
	next-trip card can offer the same one-tap navigation. Read-only."""
	if not route_plan:
		return None
	from apex_habitat.salis.api import masar

	for stop in masar._ordered_stops(route_plan):  # read-only reuse; masar unedited
		pickup = stop.get("pickup") or {}
		if pickup.get("google_maps_url"):
			return pickup["google_maps_url"]
	return None


def _vehicle_last_site_maps_url(vehicle):
	"""The Maps deep-link for the vehicle's last-known site, or None.

	Salis Vehicle records no GPS/coordinate field, so "last-known site" is derived
	from where the vehicle was last operated: the most recent Dispatch Trip's route
	first mapped stop. Reuses ``_route_first_stop_maps_url`` (read-only); returns None
	when the vehicle has no trip with a mappable route, so the card omits the link."""
	if not vehicle:
		return None
	rp = frappe.db.get_value(
		"Dispatch Trip",
		{"vehicle": vehicle, "route_plan": ["is", "set"]},
		"route_plan",
		order_by="trip_date desc, creation desc",
	)
	return _route_first_stop_maps_url(rp)


def _attach_trip_maps(trips):
	"""Stamp each trip with ``google_maps_url`` (its first mapped stop's deep-link).
	Must run BEFORE ``_label_trips`` overwrites ``route_plan`` with the route name."""
	cache = {}
	for t in trips:
		rp = t.get("route_plan")
		if rp and rp not in cache:
			cache[rp] = _route_first_stop_maps_url(rp)
		t["google_maps_url"] = cache.get(rp)


def _attach_trip_log_state(trips, driver):
	"""Stamp each trip card with its Trip Start Log state (started / log status) so the
	driver's Trips list can show start/complete without a per-card round-trip. One query
	keyed on the driver's logs for the listed trips; trips with no log read as not started."""
	names = [t["name"] for t in trips if t.get("name")]
	if not names:
		return
	logs = frappe.get_all(
		"Trip Start Log",
		filters={"dispatch_trip": ["in", names], "driver": driver, "docstatus": ["<", 2]},
		fields=["dispatch_trip", "status"],
	)
	by_trip = {row["dispatch_trip"]: row.get("status") for row in logs}
	for t in trips:
		status = by_trip.get(t["name"])
		t["started"] = t["name"] in by_trip
		t["trip_log_status"] = status


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


def _today_attendance_state(driver):
	"""Today's attendance state for ``driver`` as the portal's display shape (read).

	The single source of truth shared by ``get_today_attendance`` and the
	``get_my_today`` composite, so both render identically. Returns the durable
	Driver Attendance fields (Time fields stringified for JSON) plus the
	``exists``/``checked_in``/``checked_out`` flags; the not-recorded-yet case
	returns the same shape with null times and never creates a row."""
	row = frappe.db.get_value(
		"Driver Attendance",
		{"driver": driver, "attendance_date": frappe.utils.today(), "docstatus": ["<", 2]},
		["name", "status", "check_in", "check_out", "worked_hours"],
		as_dict=True,
	)
	if not row:
		return {
			"exists": False,
			"checked_in": False,
			"checked_out": False,
			"status": None,
			"check_in": None,
			"check_out": None,
			"worked_hours": None,
		}
	check_in = frappe.utils.cstr(row.get("check_in")) if row.get("check_in") else None
	check_out = frappe.utils.cstr(row.get("check_out")) if row.get("check_out") else None
	return {
		"exists": True,
		"checked_in": bool(check_in),
		"checked_out": bool(check_out),
		"status": row.get("status"),
		"check_in": check_in,
		"check_out": check_out,
		"worked_hours": row.get("worked_hours"),
	}


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


# [#clropn] A driver is "not cleared" while an exit clearance is still in any
# unresolved state — Cleared/Cancelled are the only terminal states.
_OPEN_CLEARANCE_STATUSES = ("Open", "In Progress", "Blocked")


def _bound_vehicle(driver):
	"""The vehicle bound to ``driver`` (current_vehicle, else Active Assignment), or None.
	Same binding rule ``_vehicle_bound_to_driver`` enforces for fuel writes."""
	vehicle = frappe.db.get_value("Salis Driver", driver, "current_vehicle")
	if vehicle:
		return vehicle
	return frappe.db.get_value(
		"Vehicle Assignment", {"driver": driver, "status": "Active"}, "vehicle"
	)


def _license_countdown(driver):
	"""The driver's licence expiry with a server-computed near-/over-expiry state.

	Mirrors ``_vehicle_compliance``: ``days_to_expiry`` is a signed int (negative =
	already expired) and ``state`` is ``expired`` | ``expiring`` (<= 30 days) |
	``valid``, so the SPA needs no date math. Returns null fields when the driver
	records no licence expiry."""
	expiry = frappe.db.get_value("Salis Driver", driver, "license_expiry")
	if not expiry:
		return {"expiry_date": None, "days_to_expiry": None, "state": None}
	days = frappe.utils.date_diff(expiry, frappe.utils.getdate())
	return {
		"expiry_date": frappe.utils.cstr(expiry),
		"days_to_expiry": days,
		"state": "expired" if days < 0 else ("expiring" if days <= 30 else "valid"),
	}


def _next_trip_today(driver):
	"""The driver's next actionable Dispatch Trip today, or None.

	"Next" is the earliest-departing trip that is not yet Completed/Cancelled.
	Route/vehicle link ids are swapped for their human labels (same as
	``my_trips_today``), and the trip's Trip Start Log state is attached so the
	portal can show whether execution has started without a second round-trip."""
	trips = frappe.get_all(
		"Dispatch Trip",
		filters={
			"driver": driver,
			"trip_date": frappe.utils.today(),
			"status": ["not in", ("Completed", "Cancelled")],
		},
		fields=["name", "route_plan", "vehicle", "depart_time", "return_time", "status"],
		order_by="depart_time asc",
		limit=1,
	)
	if not trips:
		return None
	trip = trips[0]
	_attach_trip_maps([trip])  # one-tap Maps before _label_trips overwrites route_plan
	_label_trips([trip])
	log = frappe.db.get_value(
		"Trip Start Log",
		{"dispatch_trip": trip["name"], "driver": driver, "docstatus": ["<", 2]},
		["status", "start_datetime"],
		as_dict=True,
	)
	trip["started"] = bool(log)
	trip["trip_log_status"] = log.get("status") if log else None
	trip["start_datetime"] = (
		frappe.utils.cstr(log["start_datetime"]) if log and log.get("start_datetime") else None
	)
	return trip


@frappe.whitelist()
def get_my_today():
	"""One composite "today" payload for the driver Home screen (read).

	Identity-scoped: the driver is resolved from the session, never client-supplied.
	Collapses what the Home screen otherwise stitches from several endpoints into a
	single read so the dashboard paints in one round-trip:

	* ``attendance``      — today's attendance state (see ``_today_attendance_state``)
	* ``next_trip``       — the next not-done Dispatch Trip today (labelled, with its
	                        Trip Start Log state), or null
	* ``license``         — licence expiry + server-computed countdown/state
	* ``vehicle_bound``   — the driver has a vehicle bound (current or active assignment)
	* ``open_clearance``  — an exit clearance is still unresolved for the driver

	Read-only, no commit. Blocked (403) when the portal is disabled or the caller is
	not a linked driver."""
	_require_enabled()
	driver = _resolve_driver()
	return {
		"attendance": _today_attendance_state(driver),
		"next_trip": _next_trip_today(driver),
		"license": _license_countdown(driver),
		"vehicle_bound": bool(_bound_vehicle(driver)),
		"open_clearance": bool(
			frappe.db.exists(
				"Driver Clearance",
				{
					"driver": driver,
					"status": ["in", _OPEN_CLEARANCE_STATUSES],
					"docstatus": ["<", 2],
				},
			)
		),
	}


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


def _vehicle_bound_to_driver(driver, vehicle):
	"""True when ``vehicle`` is genuinely bound to ``driver``.

	A vehicle is bound when it is the driver's ``current_vehicle`` OR the driver
	holds an Active Vehicle Assignment for it. This is the server-side guard that
	stops a driver from charging fuel against a vehicle that is not theirs by
	passing an arbitrary ``vehicle`` id to the portal."""
	if not vehicle:
		return False
	if frappe.db.get_value("Salis Driver", driver, "current_vehicle") == vehicle:
		return True
	return bool(
		frappe.db.exists(
			"Vehicle Assignment",
			{"driver": driver, "vehicle": vehicle, "status": "Active"},
		)
	)


@frappe.whitelist(methods=["POST"])
def submit_fuel_request(litres, fuel_platform=None, vehicle=None):
	_require_enabled()
	driver = _resolve_driver()
	vehicle = vehicle or frappe.db.get_value("Salis Driver", driver, "current_vehicle")
	if not vehicle:
		frappe.throw(_("No vehicle is assigned to you. Ask your supervisor to assign one before requesting fuel."))
	# [#c6nmir]
	if not _vehicle_bound_to_driver(driver, vehicle):
		frappe.throw(
			_("That vehicle is not assigned to you. You can only request fuel for your own vehicle."),
			frappe.PermissionError,
		)
	doc = frappe.get_doc(
		{"doctype": "Fuel Request", "driver": driver, "vehicle": vehicle,
		 "fuel_platform": fuel_platform, "requested_litres": frappe.utils.flt(litres),
		 "request_date": frappe.utils.today(), "status": "Pending"}
	)
	doc.insert(ignore_permissions=True)  # audit-ok — driver resolved server-side
	return {"name": doc.name}


@frappe.whitelist()
def my_fuel_quota(vehicle=None):
	"""This month's Fuel Quota for the driver's bound vehicle (read).

	Identity-scoped: the driver is resolved from the session, never client-supplied.
	``vehicle`` is optional and, when given, is honoured only after the same binding
	check fuel writes use (``_vehicle_bound_to_driver``) — so a driver can never read
	another vehicle's quota by guessing an id; an unbound id falls back to the bound
	vehicle. The quota row is the native Fuel Quota for (vehicle, this YYYY-MM period),
	the same record the fuel engine keeps ``consumed_litres`` on.

	Returns ``{"has_quota": False, ...}`` (a friendly empty state, never a 403) when no
	vehicle is bound or no quota exists for the month, so the SPA omits the card.
	``remaining_litres`` is server-computed (clamped at 0) so both languages render the
	same number with no client math. Read-only, no commit."""
	_require_enabled()
	driver = _resolve_driver()

	if not vehicle or not _vehicle_bound_to_driver(driver, vehicle):
		vehicle = _bound_vehicle(driver)
	# Approval threshold (litres) so the Fuel screen can state which requests need
	# approval; 0/blank on the Single means "no threshold" (every request auto-flows).
	threshold = frappe.utils.flt(
		frappe.db.get_single_value("Salis Settings", "fuel_request_approval_threshold_litres")
	)
	if not vehicle:
		return {"has_quota": False, "vehicle": None, "approval_threshold_litres": threshold}

	period_month = frappe.utils.today()[:7]
	row = frappe.db.get_value(
		"Fuel Quota",
		{"vehicle": vehicle, "period_month": period_month, "docstatus": ["<", 2]},
		["name", "monthly_litres", "monthly_amount", "consumed_litres", "status"],
		as_dict=True,
	)
	if not row:
		return {
			"has_quota": False,
			"vehicle": vehicle,
			"period_month": period_month,
			"approval_threshold_litres": threshold,
		}

	monthly = frappe.utils.flt(row.get("monthly_litres"))
	consumed = frappe.utils.flt(row.get("consumed_litres"))
	return {
		"has_quota": True,
		"vehicle": vehicle,
		"period_month": period_month,
		"monthly_litres": monthly,
		"monthly_amount": frappe.utils.flt(row.get("monthly_amount")),
		"consumed_litres": consumed,
		"remaining_litres": max(monthly - consumed, 0),
		"status": row.get("status"),
		"approval_threshold_litres": threshold,
	}


@frappe.whitelist()
def my_fuel_requests(limit=30):
	"""The current driver's OWN fuel-request history (read).

	Identity-scoped via endpoint-scoped ``get_all`` (the ``my_trips_today`` precedent):
	the driver is resolved from the session and every row is filtered on that driver,
	so this can only return the caller's own requests — the client never supplies a
	driver id. The Driver role holds no read DocPerm on Fuel Request by design (it is a
	staff/oversight-read DocType); the endpoint itself is the authorization boundary, so
	no Driver if_owner DocPerm is added (see the read-access decision on this endpoint).

	Each row carries the request date, requested litres, status, and the Fuel Platform's
	display label (link id swapped for ``platform_name`` like the trip cards), newest
	first. Read-only, no commit."""
	_require_enabled()
	driver = _resolve_driver()
	rows = frappe.get_all(
		"Fuel Request",
		filters={"driver": driver, "docstatus": ["<", 2]},
		fields=["name", "request_date", "requested_litres", "status", "fuel_platform"],
		order_by="request_date desc, creation desc",
		limit=frappe.utils.cint(limit) or 30,
	)
	platforms = {r["fuel_platform"] for r in rows if r.get("fuel_platform")}
	labels = {}
	if platforms:
		for p in frappe.get_all(
			"Fuel Platform",
			filters={"name": ["in", list(platforms)]},
			fields=["name", "platform_name"],
		):
			labels[p["name"]] = p.get("platform_name") or p["name"]
	for r in rows:
		r["request_date"] = frappe.utils.cstr(r["request_date"]) if r.get("request_date") else None
		r["requested_litres"] = frappe.utils.flt(r.get("requested_litres"))
		if r.get("fuel_platform"):
			r["fuel_platform"] = labels.get(r["fuel_platform"], r["fuel_platform"])
	return rows


@frappe.whitelist()
def my_worker_route_today():
    """The current driver's worker-transport route today (read), surfaced in the
    driver portal's "My Route" screen.

    Thin identity-scoped wrapper over ``salis.api.masar.get_my_worker_route_today``
    (which resolves the session user to a Salis Driver server-side). Lives here so
    the driver SPA calls one cohesive driver-portal API namespace. Read-only."""
    from apex_habitat.salis.api import masar

    return masar.get_my_worker_route_today()


@frappe.whitelist()
def my_trip_route(dispatch_trip):
    """One trip's ordered route for the current driver (read).

    Backs the driver portal's per-trip drill-in: tapping a "My Trips" card opens
    this single Dispatch Trip's ordered stops. Identity-scoped — the driver is
    resolved from the session, never client-supplied — and the trip is returned
    only when it belongs to that driver, so one driver can never read another's
    trip by guessing a ``dispatch_trip`` id.

    Reuses masar's read-only stop-ordering (``_ordered_stops``) so the timeline
    shape matches the all-trips route view exactly; masar is imported, not edited.
    A trip with no ``route_plan`` (e.g. an Administrative Trip, excluded from the
    worker route) returns ``has_route_plan = False`` with an empty ``stops`` list,
    letting the SPA show an explicit "no route planned" state rather than a blank.
    Read-only, no commit, no GL."""
    _require_enabled()
    driver = _resolve_driver()

    trip = frappe.db.get_value(
        "Dispatch Trip",
        {"name": dispatch_trip, "driver": driver},
        ["name", "route_plan", "vehicle", "depart_time", "return_time", "status"],
        as_dict=True,
    )
    # [#t170nf] Unknown id OR a trip that isn't this driver's both fail closed.
    if not trip:
        frappe.throw(_("Trip not found."), frappe.DoesNotExistError)

    from apex_habitat.salis.api import masar

    route_plan = trip.get("route_plan")
    stops = masar._ordered_stops(route_plan)  # read-only reuse; masar unedited

    vehicle = trip.get("vehicle")
    if vehicle:
        vehicle = frappe.db.get_value("Salis Vehicle", vehicle, "plate_number") or vehicle

    return {
        "dispatch_trip": trip["name"],
        "route_plan": route_plan,
        "route_name": (
            (frappe.db.get_value("Route Plan", route_plan, "route_name") or route_plan)
            if route_plan
            else None
        ),
        "vehicle": vehicle,
        "depart_time": masar._fmt_time(trip.get("depart_time")),
        "return_time": masar._fmt_time(trip.get("return_time")),
        "status": trip.get("status"),
        "has_route_plan": bool(route_plan),
        "stops": stops,
    }


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
	# Native Communications threaded against the Issue, oldest first (the reply log).
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
		# strip markup so the SPA renders a clean line, not raw HTML
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
	# A driver reply revives a closed ticket so staff re-engage.
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
	# Vehicle context goes into the body (Issue has no native vehicle link).
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


def _resolve_my_trip(dispatch_trip, driver):
	"""The Dispatch Trip ``dispatch_trip`` only when it belongs to ``driver``, else
	fail closed. Shared scope guard for the trip-execution writes so one driver can
	never start/complete another driver's trip by guessing an id."""
	trip = frappe.db.get_value(
		"Dispatch Trip",
		{"name": dispatch_trip, "driver": driver},
		["name", "vehicle", "route_plan", "transport_request", "trip_date"],
		as_dict=True,
	)
	if not trip:
		frappe.throw(_("Trip not found."), frappe.DoesNotExistError)
	return trip


def _trip_log_state(driver, dispatch_trip):
	"""The driver's Trip Start Log state for a trip as the portal's display shape.
	Mirrors the projection ``_next_trip_today`` attaches, so a start/complete response
	updates the card reactively with no extra round-trip."""
	log = frappe.db.get_value(
		"Trip Start Log",
		{"dispatch_trip": dispatch_trip, "driver": driver, "docstatus": ["<", 2]},
		["name", "status", "start_datetime", "end_datetime"],
		as_dict=True,
	)
	if not log:
		return {"started": False, "trip_log_status": None, "start_datetime": None, "end_datetime": None}
	return {
		"started": True,
		"name": log["name"],
		"trip_log_status": log.get("status"),
		"start_datetime": frappe.utils.cstr(log["start_datetime"]) if log.get("start_datetime") else None,
		"end_datetime": frappe.utils.cstr(log["end_datetime"]) if log.get("end_datetime") else None,
	}


@frappe.whitelist(methods=["POST"])
def start_my_trip(dispatch_trip):
	"""Mark the driver's own trip Started, creating its Trip Start Log (write).

	Identity-scoped: the driver is resolved from the session and the trip is honoured
	only when it belongs to that driver (``_resolve_my_trip``). Gets-or-creates the
	Trip Start Log for (trip, driver) and stamps ``start_datetime``; idempotent — a
	second tap returns the existing state rather than duplicating. The Driver holds an
	``if_owner`` DocPerm on Trip Start Log, and the write is server-authoritative
	(driver resolved from session), so ``ignore_permissions`` is set. No GL — Trip Start
	Log is a headcount/execution record only."""
	_require_enabled()
	driver = _resolve_driver()
	trip = _resolve_my_trip(dispatch_trip, driver)
	existing = frappe.db.get_value(
		"Trip Start Log",
		{"dispatch_trip": dispatch_trip, "driver": driver, "docstatus": ["<", 2]},
		"name",
	)
	if not existing:
		doc = frappe.get_doc(
			{
				"doctype": "Trip Start Log",
				"dispatch_trip": dispatch_trip,
				"driver": driver,
				"vehicle": trip.get("vehicle"),
				"trip_date": trip.get("trip_date") or frappe.utils.today(),
				"status": "Started",
				"start_datetime": frappe.utils.now_datetime(),
			}
		)
		doc.insert(ignore_permissions=True)  # audit-ok — driver resolved server-side
	return _trip_log_state(driver, dispatch_trip)


@frappe.whitelist(methods=["POST"])
def complete_my_trip(dispatch_trip):
	"""Mark the driver's own trip Completed on its Trip Start Log (write).

	Identity-scoped (``_resolve_my_trip``). Updates the existing log's status to
	Completed and stamps ``end_datetime``; if the driver never tapped start, the log is
	created and immediately completed so the day still records execution. Server-
	authoritative, so ``ignore_permissions`` is set. No GL."""
	_require_enabled()
	driver = _resolve_driver()
	trip = _resolve_my_trip(dispatch_trip, driver)
	name = frappe.db.get_value(
		"Trip Start Log",
		{"dispatch_trip": dispatch_trip, "driver": driver, "docstatus": ["<", 2]},
		"name",
	)
	if name:
		doc = frappe.get_doc("Trip Start Log", name)
	else:
		doc = frappe.get_doc(
			{
				"doctype": "Trip Start Log",
				"dispatch_trip": dispatch_trip,
				"driver": driver,
				"vehicle": trip.get("vehicle"),
				"trip_date": trip.get("trip_date") or frappe.utils.today(),
				"start_datetime": frappe.utils.now_datetime(),
			}
		)
	doc.status = "Completed"
	if not doc.end_datetime:
		doc.end_datetime = frappe.utils.now_datetime()
	doc.flags.ignore_permissions = True  # audit-ok — driver resolved from session identity
	doc.save() if not doc.is_new() else doc.insert()
	return _trip_log_state(driver, dispatch_trip)


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


@frappe.whitelist()
def get_my_notifications(limit=20):
	"""The current user's recent native Notification Log rows (read).

	Identity-scoped: filtered to ``for_user = session user`` (never client-supplied),
	so it only ever returns the caller's own notifications. These are the system
	notifications native Frappe writes when a Salis Notification with
	``send_system_notification`` fires at the driver's user — the driver-facing
	channels (blocked-driver clearance, fuel-overdue, vehicle-compliance, trip
	scheduled). Backs the Home screen's notifications strip/bell.

	Each row carries subject, a plain-text body (the email_content stripped of HTML),
	the read flag, and a stringified ``creation`` timestamp (newest first). Read-only,
	no commit; never raises for a driver with no notifications (returns an empty list).
	"""
	_require_enabled()
	_resolve_driver()  # gate: only a linked driver sees the feed
	rows = frappe.get_all(
		"Notification Log",
		filters={"for_user": frappe.session.user},
		fields=["name", "subject", "email_content", "read", "creation", "document_type", "document_name"],
		order_by="creation desc",
		limit=frappe.utils.cint(limit) or 20,
	)
	for r in rows:
		r["read"] = bool(r.get("read"))
		r["creation"] = frappe.utils.cstr(r["creation"]) if r.get("creation") else None
		# strip the notification's HTML so the SPA renders a clean line, not markup
		r["body"] = frappe.utils.strip_html_tags(r.get("email_content") or "").strip() or None
		r.pop("email_content", None)
	return rows
