# Copyright (c) 2026, AFMCO and contributors
"""Salis Driver Portal — identity-scoped, no-financial-impact APIs for the mobile
SPA at /driver. Every endpoint resolves the CURRENT user to a Salis Driver and acts
only on that driver's records; the client never supplies the driver id."""

import frappe
from frappe import _

# Maps deep-link builders shared with masar so worker + driver match; _stop_waypoint
# is re-exported here for callers importing it from this module (maps_links is pure).
from apex.salis.api.maps_links import _full_route_maps_url as _chain_route_maps_url
from apex.salis.api.maps_links import _stop_waypoint  # noqa: F401  (re-exported)
from apex.salis.utils import get_driver_for_user


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

def _license_warn_days():
	"""Days-to-expiry at/below which a licence or vehicle compliance document is
	flagged ``expiring`` (the amber/red threshold). Read from Salis Settings via the
	zero-trap helper so a blank/0 Single value keeps today's 30-day window."""
	from apex.apex_core.doctype.salis_settings.salis_settings import get_salis_int

	return get_salis_int("license_expiring_warn_days", 30)

def _find_driver(user=None):
	"""Return the Salis Driver name linked to the session user, or None.

	Thin alias of the shared ``salis.utils.get_driver_for_user`` (the single
	resolver). Soft lookup with no exception — the portal bootstrap (and masar,
	which imports ``_resolve_driver``) relies on an unlinked user getting a
	friendly screen instead of a 403."""
	return get_driver_for_user(user)

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

def _full_route_maps_url(route_plan):
	"""A single Google Maps directions URL chaining a route plan's ordered stops,
	or None when fewer than two stops are navigable.

	Resolves the plan via masar's read-only ``_ordered_stops`` (so the sequence
	matches the route view exactly), then delegates to the shared list-based
	chainer so the driver's deep-link is identical to the worker's. Read-only."""
	from apex.salis.api import masar

	return _chain_route_maps_url(masar._ordered_stops(route_plan))

def _route_first_stop_maps_url(route_plan):
	"""The Google Maps deep-link for a route plan's first mapped stop, or None.

	Reuses masar's read-only ``_ordered_stops`` so the URL is the exact one the
	Route screen already renders. Returns the first stop pickup that carries a
	``google_maps_url`` (the trip's first navigable destination), so a Trips/
	next-trip card can offer the same one-tap navigation. Read-only."""
	if not route_plan:
		return None
	from apex.salis.api import masar

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

def _attach_boarding_counts(trips, driver):
	"""Stamp each trip card with boarded / expected headcount for an "N of M boarded"
	progress line. ``boarded_count`` comes from the trip's Trip Start Log (the
	controller derives it from the boarding-event rows); ``expected_count`` is the
	linked Transport Request's manifest size — read directly so a trip with no log
	yet still shows "0 of M". One query per side keyed on the listed trips."""
	names = [t["name"] for t in trips if t.get("name")]
	if not names:
		return
	logs = frappe.get_all(
		"Trip Start Log",
		filters={"dispatch_trip": ["in", names], "driver": driver, "docstatus": ["<", 2]},
		fields=["dispatch_trip", "boarded_count"],
	)
	boarded_by_trip = {
		row["dispatch_trip"]: frappe.utils.cint(row.get("boarded_count")) for row in logs
	}
	# Expected = the trip's Transport Request manifest size (worker_count).
	requests = {t.get("transport_request") for t in trips if t.get("transport_request")}
	expected_by_request = {}
	if requests:
		for r in frappe.get_all(
			"Transport Request",
			filters={"name": ["in", list(requests)]},
			fields=["name", "worker_count"],
		):
			expected_by_request[r["name"]] = frappe.utils.cint(r.get("worker_count"))
	for t in trips:
		t["boarded_count"] = boarded_by_trip.get(t["name"], 0)
		t["expected_count"] = expected_by_request.get(t.get("transport_request"), 0)

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
	warn_days = _license_warn_days()
	return {
		"expiry_date": frappe.utils.cstr(expiry),
		"days_to_expiry": days,
		"state": "expired" if days < 0 else ("expiring" if days <= warn_days else "valid"),
	}

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

def _open_trip_log(dispatch_trip, driver):
	"""The driver's open (draft) Trip Start Log doc for a trip, or None. Stop progress
	is only kept on the live draft log — a submitted/cancelled log is closed."""
	name = frappe.db.get_value(
		"Trip Start Log",
		{"dispatch_trip": dispatch_trip, "driver": driver, "docstatus": 0},
		"name",
	)
	return frappe.get_doc("Trip Start Log", name) if name else None

def _stop_progress_map(dispatch_trip, driver):
	"""``{route_stop: {done, done_at}}`` from the trip's open Trip Start Log, so the
	route view can reflect persisted per-stop completion on reload. Keyed on the source
	Route Stop row name (stable across reloads). Empty when the trip isn't started."""
	log = _open_trip_log(dispatch_trip, driver)
	if not log:
		return {}
	out = {}
	for row in log.stop_progress or []:
		if row.route_stop:
			out[row.route_stop] = {
				"done": bool(row.done),
				"done_at": frappe.utils.cstr(row.done_at) if row.done_at else None,
				"arrived": bool(row.arrived),
				"arrived_at": frappe.utils.cstr(row.arrived_at) if row.arrived_at else None,
			}
	return out

def _route_stop_names(route_plan):
	"""The Route Stop child row names for a plan, in the SAME order masar._ordered_stops
	returns its stops (idx asc) — so they zip 1:1 onto that list to give each
	stop a stable identity for progress tracking. masar drops the row name, so it is
	re-fetched here. Read-only."""
	if not route_plan:
		return []
	return frappe.get_all(
		"Route Stop",
		filters={"parent": route_plan, "parenttype": "Route Plan"},
		pluck="name",
		order_by="idx asc",
	)

def _attach_stop_progress(stops, route_plan, dispatch_trip, driver):
	"""Stamp each ordered stop with its ``route_stop`` (stable Route Stop row name) and
	persisted ``done``/``done_at`` from the trip's open Trip Start Log. Mutates in place;
	a not-started trip leaves every stop ``done=False``."""
	if not stops:
		return
	names = _route_stop_names(route_plan)
	progress = _stop_progress_map(dispatch_trip, driver)
	for i, stop in enumerate(stops):
		rs = names[i] if i < len(names) else None
		stop["route_stop"] = rs
		state = progress.get(rs) if rs else None
		stop["done"] = bool(state and state.get("done"))
		stop["done_at"] = state.get("done_at") if state else None
		stop["arrived"] = bool(state and state.get("arrived"))
		stop["arrived_at"] = state.get("arrived_at") if state else None


@frappe.whitelist(methods=["POST"])
def mark_arrived(dispatch_trip, route_stop, arrived=1, sequence=None, stop_name=None):
	"""Driver action: "I've arrived at this pickup stop" (write).

	The explicit arrival signal P-046 surfaces to the workers waiting at that stop.
	Reuses the SAME Trip Stop Progress rail ``mark_stop_progress`` writes (one row
	per route stop, keyed on the stable ``route_stop`` row name) — arrival is a new
	flag on that row, not a new record — so the driver's per-stop state stays in one
	place. Identity-scoped (``_resolve_my_trip``) and requires the trip to be started
	(an open Trip Start Log must exist). Idempotent and reversible: ``arrived=0``
	clears it; re-marking the same state is a no-op.

	On arrival it publishes ``boarding_arrived`` to the Dispatch Trip room (the P-032
	after_commit pattern, via the boarding flow's shared ``_publish``) so socketed
	clients refresh; the durable arrival state on the row is what the guest worker
	poll (``worker_trip_boarding``) reads — the delivery path for the worker's Masar
	app, since guests have no socket. Server-authoritative, so ``ignore_permissions``
	is set. No GL."""
	from apex.salis.api.boarding_flow import _publish

	_require_enabled()
	driver = _resolve_driver()
	_resolve_my_trip(dispatch_trip, driver)  # enforces own-trip; raises if not
	log = _open_trip_log(dispatch_trip, driver)
	if not log:
		# Arrival lives on the trip log, so the trip must be started first.
		frappe.throw(_("Start the trip before marking arrival."))

	arrived = frappe.utils.cint(arrived)
	existing = next((r for r in (log.stop_progress or []) if r.route_stop == route_stop), None)
	if existing:
		existing.arrived = arrived
		existing.arrived_at = frappe.utils.now_datetime() if arrived else None
	else:
		log.append(
			"stop_progress",
			{
				"route_stop": route_stop,
				"sequence": frappe.utils.cint(sequence) if sequence is not None else None,
				"stop_name": stop_name,
				"arrived": arrived,
				"arrived_at": frappe.utils.now_datetime() if arrived else None,
			},
		)
	log.flags.ignore_permissions = True  # audit-ok — driver resolved from session identity
	log.save()

	# P-032: tell the trip room so any socketed client refreshes; the worker poll
	# (worker_trip_boarding) carries the durable state for the guest Masar app.
	if arrived:
		_publish("boarding_arrived", dispatch_trip, {"route_stop": route_stop})

	return {
		"route_stop": route_stop,
		"arrived": bool(arrived),
		"stop_progress": _stop_progress_map(dispatch_trip, driver),
	}

@frappe.whitelist(methods=["POST"])
def save_push_subscription(endpoint, p256dh=None, auth=None, user_agent=None):
	"""Store (or refresh) the driver's Web Push subscription on opt-in (write).

	Identity-scoped: the driver is resolved from the session, never client-supplied, so
	a subscription is always bound to the caller's own driver. The browser passes its
	PushSubscription endpoint + keys; the endpoint is unique, so a re-subscribe on the
	same device updates the existing row (re-enabling it and refreshing its keys) rather
	than duplicating. Refused (403) when push is not configured, so the client cannot
	bank a subscription against a portal that can never deliver. Returns ``{"name": ...}``.
	"""
	_require_enabled()
	driver = _resolve_driver()
	endpoint = (endpoint or "").strip()
	if not endpoint:
		frappe.throw(_("A push subscription endpoint is required."))

	from apex.salis.api import web_push

	if not web_push.is_configured():
		frappe.throw(_("Background notifications are not enabled."), frappe.PermissionError)

	# SSRF gate: ``endpoint`` is client-supplied and later becomes a server-side POST
	# target, so refuse anything but an https:// URL on a known push provider — blocks
	# aiming the server at an internal/loopback/metadata host. See web_push allowlist.
	if not web_push.is_allowed_push_endpoint(endpoint):
		frappe.throw(_("This push subscription endpoint is not allowed."))

	existing = frappe.db.get_value("Driver Push Subscription", {"endpoint": endpoint}, "name")
	doc = (
		frappe.get_doc("Driver Push Subscription", existing)
		if existing
		else frappe.new_doc("Driver Push Subscription")
	)
	doc.update(
		{
			"driver": driver,
			"user": frappe.session.user,
			"endpoint": endpoint,
			"p256dh": p256dh,
			"auth": auth,
			"user_agent": user_agent,
			"enabled": 1,
			"last_seen": frappe.utils.now_datetime(),
		}
	)
	doc.save(ignore_permissions=True)  # audit-ok — driver resolved from session identity
	return {"name": doc.name}


# ---------------------------------------------------------------------------
# Public endpoint re-exports (P-180). Keep the canonical dotted path
# apex.salis.api.driver_portal.<endpoint> resolving here after the
# domain split, so every frontend/test/notification caller is unaffected.
# ---------------------------------------------------------------------------
from apex.salis.api.driver_portal.profile import (  # noqa: E402
    get_driver_context,
    get_driver_profile,
    get_my_vehicle,
)
from apex.salis.api.driver_portal.trips import (  # noqa: E402
    my_trips_today,
    my_trips_recent,
    my_worker_route_today,
    my_trip_route,
)
from apex.salis.api.driver_portal.attendance import (  # noqa: E402
    get_today_attendance,
    my_attendance,
    driver_check_in,
    driver_check_out,
)
from apex.salis.api.driver_portal.fuel import (  # noqa: E402
    submit_fuel_request,
    my_fuel_quota,
    my_fuel_requests,
)
from apex.salis.api.driver_portal.support import (  # noqa: E402
    my_support_tickets,
    raise_support_ticket,
    get_ticket,
    reply_to_ticket,
    report_vehicle_problem,
    request_license_renewal,
)
from apex.salis.api.driver_portal.boarding import (  # noqa: E402
    manual_boarding_sheet,
    manual_board_workers,
)
from apex.salis.api.driver_portal.execution import (  # noqa: E402
    start_my_trip,
    complete_my_trip,
    push_driver_position,
    mark_stop_progress,
)
from apex.salis.api.driver_portal.clearance import (  # noqa: E402
    my_clearance,
)
from apex.salis.api.driver_portal.notifications import (  # noqa: E402
    get_my_notifications,
    get_push_config,
    delete_push_subscription,
)
from apex.salis.api.driver_portal.home import (  # noqa: E402
    get_my_today,
)
