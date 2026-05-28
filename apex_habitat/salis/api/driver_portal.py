"""Salis Driver Portal — identity-scoped, no-financial-impact APIs for the mobile
SPA at /driver. Every endpoint resolves the CURRENT user to a Salis Driver and acts
only on that driver's records; the client never supplies the driver id."""

import frappe
from frappe import _


def _portal_enabled():
	return bool(frappe.db.get_single_value("Salis Settings", "enable_driver_portal"))


def _resolve_driver(user=None):
	"""Return the Salis Driver name linked to the session user, else 403."""
	user = user or frappe.session.user
	driver = None
	employee = frappe.db.get_value("Employee", {"user_id": user}, "name")
	if employee:
		driver = frappe.db.get_value("Salis Driver", {"employee": employee}, "name")
	if not driver:
		frappe.throw(_("No Salis Driver is linked to your account."), frappe.PermissionError)
	return driver


def _require_enabled():
	if not _portal_enabled():
		frappe.throw(_("Driver portal is not enabled."), frappe.PermissionError)


@frappe.whitelist()
def get_driver_context():
	"""Driver profile + portal-enabled flag (read)."""
	if not _portal_enabled():
		return {"enabled": False}
	driver = _resolve_driver()
	d = frappe.db.get_value(
		"Salis Driver", driver,
		["name", "full_name", "status", "current_vehicle", "license_expiry"],
		as_dict=True,
	)
	return {"enabled": True, "driver": d}


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


@frappe.whitelist(methods=["POST"])
def driver_check_in(photo=None):
	_require_enabled()
	driver = _resolve_driver()
	doc = _today_attendance(driver)
	doc.check_in = frappe.utils.nowtime()
	if not doc.status:
		doc.status = "Present"
	if photo:
		doc.append("images", {"image": photo, "captured_at": frappe.utils.now_datetime()})
	doc.save(ignore_permissions=True)  # audit-ok — identity resolved server-side
	frappe.db.commit()
	return {"name": doc.name, "check_in": str(doc.check_in)}


@frappe.whitelist(methods=["POST"])
def driver_check_out(photo=None):
	_require_enabled()
	driver = _resolve_driver()
	doc = _today_attendance(driver)
	doc.check_out = frappe.utils.nowtime()
	if photo:
		doc.append("images", {"image": photo, "captured_at": frappe.utils.now_datetime()})
	doc.save(ignore_permissions=True)  # audit-ok
	frappe.db.commit()
	return {"name": doc.name, "check_out": str(doc.check_out)}


@frappe.whitelist(methods=["POST"])
def submit_fuel_request(litres, fuel_platform=None, vehicle=None):
	_require_enabled()
	driver = _resolve_driver()
	vehicle = vehicle or frappe.db.get_value("Salis Driver", driver, "current_vehicle")
	if not vehicle:
		frappe.throw(_("No vehicle is assigned to you. Ask your supervisor to assign one before requesting fuel."))
	doc = frappe.get_doc(
		{"doctype": "Fuel Request", "driver": driver, "vehicle": vehicle,
		 "fuel_platform": fuel_platform, "requested_litres": frappe.utils.flt(litres),
		 "request_date": frappe.utils.today(), "status": "Pending"}
	)
	doc.insert(ignore_permissions=True)  # audit-ok — driver resolved server-side
	frappe.db.commit()
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
	frappe.db.commit()
	return {"name": doc.name}
