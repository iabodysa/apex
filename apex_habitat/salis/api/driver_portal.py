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
	_label_trips(trips)  # cards show plate / route name, not raw link ids
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
def raise_support_ticket(category, priority, subject, description):
	"""Raise a support ticket as a native ERPNext Issue (write).

	Identity-scoped: the driver is resolved from the session, never client-supplied,
	so the Issue is always stamped with the caller's own driver (``custom_driver``)
	and email (``raised_by``). The client-supplied ``category`` maps to the Issue
	Type and ``priority`` to the Issue Priority — both seeded by
	``apex_core.setup.seeders.salis_issue_seed``. A linked Service Level
	Agreement (default for Issue) is
	applied natively by ERPNext on insert, so the response/resolution clock starts
	automatically. Returns ``{"name": ...}`` exactly as before so the portal SPA is
	unchanged."""
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
	return {"name": doc.name}
