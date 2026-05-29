"""Salis Driver Portal — manual demo/test data helper.

NOT wired into install, after_migrate, or any seed. This exists purely so a
developer can, on demand, recreate a complete LINKED driver experience for the
/driver portal after a fresh install/uninstall wipes the test data.

Run on a test site only::

    bench --site <site> execute apex_habitat.salis.demo.setup_driver_demo

What it builds (every step is existence-guarded, so re-running is safe):
  * adds the ``Driver`` role to Administrator — ADDITIVE, never removes a role
  * an Employee linked to Administrator
  * a ``Salis Driver`` linked to that Employee
  * an Active ``Salis Vehicle`` + an Active ``Vehicle Assignment`` (sets
    the driver's ``current_vehicle``)
  * today's ``Driver Attendance`` for the driver
  * a sample ``Transport Request`` and a ``Dispatch Trip`` (kept as a Planned
    draft so it surfaces in ``my_trips_today`` without firing submit-time
    vehicle locking / fulfilment side effects)
  * turns ON ``Salis Settings.enable_driver_portal``

The data is bench-only and is wiped by a reinstall — that is expected; call this
again to recreate it.
"""

import frappe

DEMO_USER = "Administrator"
DEMO_PLATE = "DEMO DRV 1"


def _ensure_driver_role():
	"""Add the Driver role to Administrator if missing — additive only."""
	user = frappe.get_doc("User", DEMO_USER)
	if "Driver" not in {r.role for r in user.roles}:
		user.add_roles("Driver")  # additive — never strips existing roles
	return DEMO_USER


def _ensure_company():
	return (
		frappe.defaults.get_global_default("company")
		or (frappe.get_all("Company", limit=1) or [{"name": None}])[0]["name"]
	)


def _ensure_employee():
	"""An Employee linked to Administrator."""
	emp = frappe.db.get_value("Employee", {"user_id": DEMO_USER}, "name")
	if emp:
		return emp
	return frappe.get_doc(
		{
			"doctype": "Employee",
			"first_name": "Demo Driver",
			"user_id": DEMO_USER,
			"date_of_birth": "1990-01-01",
			"date_of_joining": frappe.utils.today(),
			"gender": "Male",
			"company": _ensure_company(),
		}
	).insert(ignore_permissions=True).name  # audit-ok — admin-only demo seeding


def _ensure_driver(employee):
	"""A Salis Driver linked to the demo Employee."""
	drv = frappe.db.get_value("Salis Driver", {"employee": employee}, "name")
	if drv:
		return drv
	return frappe.get_doc(
		{
			"doctype": "Salis Driver",
			"employee": employee,
			"full_name": "Demo Driver",
			"status": "Active",
			"supervisor": DEMO_USER,
		}
	).insert(ignore_permissions=True).name  # audit-ok — admin-only demo seeding


def _ensure_vehicle():
	"""An Active Salis Vehicle for the demo (matched by plate number)."""
	veh = frappe.db.get_value("Salis Vehicle", {"plate_number": DEMO_PLATE}, "name")
	if veh:
		if frappe.db.get_value("Salis Vehicle", veh, "status") != "Active":
			frappe.db.set_value("Salis Vehicle", veh, "status", "Active")
		return veh
	return frappe.get_doc(
		{"doctype": "Salis Vehicle", "plate_number": DEMO_PLATE, "status": "Active"}
	).insert(ignore_permissions=True).name  # audit-ok — admin-only demo seeding


def _existing_active_vehicle(driver):
	"""The vehicle bound to the driver via an existing SUBMITTED Active Vehicle
	Assignment, if any. Reused so a re-run never tries to create a second active
	assignment (the controller's no-overlap rule would reject that)."""
	va = frappe.get_all(
		"Vehicle Assignment",
		filters={"driver": driver, "status": "Active", "docstatus": 1},
		fields=["vehicle"],
		limit=1,
	)
	if va:
		return va[0]["vehicle"]
	# Fall back to the denormalised mirror if a current_vehicle is already set.
	return frappe.db.get_value("Salis Driver", driver, "current_vehicle")


def _ensure_vehicle_and_assignment(driver):
	"""Guarantee the driver has a bound Active vehicle and return it.

	Idempotent and overlap-safe: if the driver already has an Active assignment
	(or a current_vehicle), that vehicle is reused as-is. Only when the driver is
	unbound does this create a demo vehicle and a SUBMITTED Vehicle Assignment —
	submission is what writes the current_vehicle mirror (the controller sets it
	in on_submit), so the portal's fuel guard recognises the vehicle."""
	bound = _existing_active_vehicle(driver)
	if bound:
		# Keep the mirror consistent without minting a clashing assignment.
		if frappe.db.get_value("Salis Driver", driver, "current_vehicle") != bound:
			frappe.db.set_value("Salis Driver", driver, "current_vehicle", bound)
		return bound

	vehicle = _ensure_vehicle()
	va = frappe.get_doc(
		{
			"doctype": "Vehicle Assignment",
			"driver": driver,
			"vehicle": vehicle,
			"status": "Active",
			"start_date": frappe.utils.today(),
		}
	)
	va.insert(ignore_permissions=True)  # audit-ok — admin-only demo seeding
	va.submit()  # on_submit writes Salis Driver.current_vehicle = vehicle
	return vehicle


def _ensure_attendance(driver):
	"""Today's Driver Attendance for the driver."""
	if frappe.db.exists(
		"Driver Attendance",
		{"driver": driver, "attendance_date": frappe.utils.today(), "docstatus": ["<", 2]},
	):
		return
	frappe.get_doc(
		{
			"doctype": "Driver Attendance",
			"driver": driver,
			"attendance_date": frappe.utils.today(),
			"status": "Present",
		}
	).insert(ignore_permissions=True)  # audit-ok — admin-only demo seeding


def _ensure_transport_request():
	"""A sample Administrative Trip Transport Request (Desk channel)."""
	existing = frappe.db.get_value(
		"Transport Request", {"purpose": "Driver portal demo"}, "name"
	)
	if existing:
		return existing
	return frappe.get_doc(
		{
			"doctype": "Transport Request",
			"requested_by": DEMO_USER,
			"service_line": "Representatives",
			"request_type": "Administrative Trip / Document Signing",
			"destination": "City Centre",
			"purpose": "Driver portal demo",
			"source_channel": "Desk",
			"status": "New",
		}
	).insert(ignore_permissions=True).name  # audit-ok — admin-only demo seeding


def _ensure_dispatch_trip(driver, vehicle, transport_request):
	"""A sample Dispatch Trip for today, kept as a Planned DRAFT.

	my_trips_today() filters on driver + trip_date regardless of docstatus, so a
	draft surfaces in the portal without triggering the submit-time vehicle lock
	and Transport Request fulfilment side effects."""
	if frappe.db.exists(
		"Dispatch Trip", {"driver": driver, "trip_date": frappe.utils.today()}
	):
		return
	frappe.get_doc(
		{
			"doctype": "Dispatch Trip",
			"driver": driver,
			"vehicle": vehicle,
			"transport_request": transport_request,
			"trip_date": frappe.utils.today(),
			"depart_time": "08:00:00",
			"return_time": "16:00:00",
			"status": "Planned",
		}
	).insert(ignore_permissions=True)  # audit-ok — admin-only demo seeding


def setup_driver_demo():
	"""Idempotently build the full LINKED driver experience for /driver.

	Safe to run repeatedly; every step is existence-guarded. Returns a small
	summary dict of the records it ensured."""
	frappe.set_user("Administrator")

	# Turn the portal ON.
	if not frappe.db.get_single_value("Salis Settings", "enable_driver_portal"):
		frappe.db.set_single_value("Salis Settings", "enable_driver_portal", 1)

	_ensure_driver_role()
	employee = _ensure_employee()
	driver = _ensure_driver(employee)
	vehicle = _ensure_vehicle_and_assignment(driver)
	_ensure_attendance(driver)
	transport_request = _ensure_transport_request()
	_ensure_dispatch_trip(driver, vehicle, transport_request)

	frappe.db.commit()

	summary = {
		"user": DEMO_USER,
		"employee": employee,
		"driver": driver,
		"vehicle": vehicle,
		"transport_request": transport_request,
		"enable_driver_portal": bool(
			frappe.db.get_single_value("Salis Settings", "enable_driver_portal")
		),
	}
	print("Salis driver demo ready:", frappe.as_json(summary))
	print("Log in as Administrator and open /driver to see the linked experience.")
	return summary
