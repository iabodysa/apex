"""Salis Driver Portal — identity-scoped, no-financial-impact APIs for the mobile
SPA at /driver. Every endpoint resolves the CURRENT user to a Salis Driver and acts
only on that driver's records; the client never supplies the driver id."""

import frappe
from frappe import _

# Salis "staff" roles — desk operators who manage the fleet rather than drive it.
# An unlinked user holding any of these is greeted as staff (not an error) and is
# offered the relevant desk links below. Kept in sync with the page/workspace role
# lists; this is a *display* hint only — every action endpoint stays driver-scoped.
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

	# Salis workspace — any staff role.
	if user == "Administrator" or roles & set(STAFF_ROLES):
		links.append({"label": "Salis Workspace", "url": "/app/salis"})

	# Dispatch Board — operations roles that run dispatch.
	dispatch_roles = {"System Manager", "Fleet Manager", "Fleet Project Manager", "Fleet Supervisor"}
	if user == "Administrator" or roles & dispatch_roles:
		links.append({"label": "Dispatch Board", "url": "/app/salis-dispatch-board"})

	# Transport Request list — gated by real DocType read permission.
	if frappe.has_permission("Transport Request", "read", user=user):
		links.append({"label": "Transport Requests", "url": "/app/transport-request"})

	# Fuel Approval Console — finance/fleet approval roles.
	fuel_roles = {"System Manager", "Fleet Manager", "Fleet Project Manager", "Finance Manager"}
	if user == "Administrator" or roles & fuel_roles:
		links.append({"label": "Fuel Approval Console", "url": "/app/fuel-approval-console"})

	return links


def _user_full_name(user=None):
	user = user or frappe.session.user
	return frappe.utils.get_fullname(user) or user


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
		# Even disabled, tell a staff user how to reach the desk.
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
	# Stringify date fields so the HTTP JSON response always serializes. A raw
	# date object can 500 the bootstrap call, which the SPA previously mis-rendered
	# as "not linked to a driver profile".
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
	return d


@frappe.whitelist()
def get_my_vehicle():
	"""The current driver's CURRENT vehicle (read).

	Identity-scoped: resolves the driver from the session, then returns the vehicle
	bound to them — their ``current_vehicle`` if set, otherwise the vehicle on an
	Active Vehicle Assignment (the same binding rule ``_vehicle_bound_to_driver``
	enforces for writes). Returns ``{"vehicle": None}`` (a friendly empty state) when
	no vehicle is bound. Read-only, no commit."""
	_require_enabled()
	driver = _resolve_driver()

	vehicle = frappe.db.get_value("Salis Driver", driver, "current_vehicle")
	assignment = None
	if not vehicle:
		# Fall back to an Active Vehicle Assignment for this driver.
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
		["name", "plate_number", "vehicle_category", "status", "ownership", "project"],
		as_dict=True,
	) or {}

	# Surface the active-assignment start date when available (either the matched
	# fallback assignment, or — when the vehicle came from current_vehicle — the
	# driver's Active Vehicle Assignment for that same vehicle, if one exists).
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
	return frappe.get_all(
		"Dispatch Trip",
		filters={"driver": driver, "trip_date": frappe.utils.today()},
		fields=["name", "route_plan", "vehicle", "depart_time", "return_time", "status"],
		order_by="depart_time asc",
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
	if not doc.status:
		doc.status = "Present"
	if photo:
		doc.append("images", {"image": photo, "captured_at": frappe.utils.now_datetime()})
	_persist_attendance(doc)
	return {"name": doc.name, "check_in": str(doc.check_in)}


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
	doc.check_out = frappe.utils.nowtime()
	if not doc.status:
		doc.status = "Present"
	if photo:
		doc.append("images", {"image": photo, "captured_at": frappe.utils.now_datetime()})
	_persist_attendance(doc)
	return {"name": doc.name, "check_out": str(doc.check_out)}


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
	# Never trust a client-supplied vehicle: it must actually be bound to this
	# driver (their current vehicle or an Active Vehicle Assignment).
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


@frappe.whitelist(methods=["POST"])
def raise_support_ticket(category, priority, subject, description):
	"""Raise a support ticket as a native ERPNext Issue (write).

	Identity-scoped: the driver is resolved from the session, never client-supplied,
	so the Issue is always stamped with the caller's own driver (``custom_driver``)
	and email (``raised_by``). The client-supplied ``category`` maps to the Issue
	Type and ``priority`` to the Issue Priority — both seeded by
	``salis.issue_seed``. A linked Service Level Agreement (default for Issue) is
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
	# Only set the masters when they exist as seeded records, so a partially
	# seeded site never trips Link validation on insert.
	if category and frappe.db.exists("Issue Type", category):
		data["issue_type"] = category
	if priority and frappe.db.exists("Issue Priority", priority):
		data["priority"] = priority
	if project:
		data["project"] = project
	doc = frappe.get_doc(data)
	doc.insert(ignore_permissions=True)  # audit-ok — driver resolved server-side
	return {"name": doc.name}
