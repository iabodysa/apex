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
	"""The current driver's support tickets (read)."""
	_require_enabled()
	driver = _resolve_driver()
	return frappe.get_all(
		"Support Ticket",
		filters={"driver": driver},
		fields=["name", "category", "priority", "subject", "status", "creation"],
		order_by="creation desc",
		limit=50,
	)


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


@frappe.whitelist(methods=["POST"])
def raise_support_ticket(category, priority, subject, description):
	_require_enabled()
	driver = _resolve_driver()
	doc = frappe.get_doc(
		{"doctype": "Support Ticket", "driver": driver, "raised_by": frappe.session.user,
		 "category": category, "priority": priority, "subject": subject,
		 "description": description, "status": "New"}
	)
	doc.insert(ignore_permissions=True)  # audit-ok
	return {"name": doc.name}
