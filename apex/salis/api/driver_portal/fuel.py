# Copyright (c) 2026, afmcoltd
"""Salis Driver Portal — fuel endpoints (split from the driver_portal god module). Kernel helpers are imported from the package so the canonical dotted path apex.salis.api.driver_portal.<fn> is unchanged."""

import frappe
from frappe import _

from apex.apex_core.utils.rate_limit_identity import rate_limit
from apex.salis.api.driver_portal import (
    _resolve_driver,
    _require_enabled,
    _bound_vehicle,
)
from apex.salis.utils import period_quota


FUEL_REQUEST_DEFAULT_LIMIT = 30
FUEL_REQUEST_MAX_LIMIT = 50


def _bounded_request_limit(value):
    """Clamps a requested fuel-history page size to the default and maximum limits."""
    parsed = frappe.utils.cint(value)
    if parsed <= 0:
        return FUEL_REQUEST_DEFAULT_LIMIT
    return min(parsed, FUEL_REQUEST_MAX_LIMIT)


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


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=10, seconds=60)
def submit_fuel_request(litres, fuel_platform=None, vehicle=None):
    """Raise a Standard Fuel Request for the driver's own vehicle (write).

	Identity-scoped: the driver is resolved credential-first and the vehicle must be
	bound to them (``_vehicle_bound_to_driver``), so fuel can never be charged to
	someone else's vehicle.

	The request carries the Fuel Quota for its OWN request month, resolved through the
	shared ``salis.utils.period_quota`` read that feeds the portal's quota bar. That is what
	makes the controller's allowance gate live: with ``fuel_quota`` empty,
	``_guard_quota_allowance`` returns at its first line and the portal draws past an
	allocation the desk and the approval console are both held to. An oversized draw is
	therefore refused here, before anything is written, with the very message the desk
	raises — the gate runs again at ``before_submit`` and inside the locked consumption
	step, which is what catches two in-flight requests that only overrun together."""
    _require_enabled()
    driver = _resolve_driver()
    vehicle = vehicle or frappe.db.get_value("Salis Driver", driver, "current_vehicle")
    if not vehicle:
        frappe.throw(_("No vehicle is assigned to you. Ask your supervisor to assign one before requesting fuel."))
    if not _vehicle_bound_to_driver(driver, vehicle):
        frappe.throw(
            _("That vehicle is not assigned to you. You can only request fuel for your own vehicle."),
            frappe.PermissionError,
        )
    request_date = frappe.utils.today()
    quota = period_quota(vehicle, request_date[:7], ["name"])
    doc = frappe.get_doc(
        {"doctype": "Fuel Request", "request_type": "Standard", "driver": driver,
         "vehicle": vehicle, "fuel_quota": quota.name if quota else None,
         "fuel_platform": fuel_platform, "requested_litres": frappe.utils.flt(litres),
         "request_date": request_date, "status": "Pending"}
    )
    doc._guard_quota_allowance()
    doc.insert(ignore_permissions=True)
    return {"name": doc.name}


@frappe.whitelist(allow_guest=True)
@rate_limit(limit=120, seconds=60)
def my_fuel_quota(vehicle=None):
    """This month's Fuel Quota for the driver's bound vehicle (read).

	Identity-scoped: the driver is resolved credential-first, never client-supplied.
	``vehicle`` is optional and, when given, is honoured only after the same binding
	check fuel writes use (``_vehicle_bound_to_driver``) — so a driver can never read
	another vehicle's quota by guessing an id; an unbound id falls back to the bound
	vehicle. The quota row is the native Fuel Quota for (vehicle, this YYYY-MM period),
	the same record the fuel engine keeps ``consumed_litres`` on — and, through the
	shared ``salis.utils.period_quota`` read, the very row ``submit_fuel_request`` binds
	a new request to, so the bar the driver sees and the allowance they are held to
	cannot disagree.

	Returns ``{"has_quota": False, ...}`` (a friendly empty state, never a 403) when no
	vehicle is bound or no quota exists for the month, so the SPA omits the card.
	``remaining_litres`` is server-computed (clamped at 0) so both languages render the
	same number with no client math. Read-only, no commit."""
    _require_enabled()
    driver = _resolve_driver()

    if not vehicle or not _vehicle_bound_to_driver(driver, vehicle):
        vehicle = _bound_vehicle(driver)
    from apex.apex_core.doctype.salis_settings.salis_settings import get_salis_float

    threshold = get_salis_float("fuel_request_approval_threshold_litres", 0.0)
    if not vehicle:
        return {"has_quota": False, "vehicle": None, "approval_threshold_litres": threshold}

    period_month = frappe.utils.today()[:7]
    row = period_quota(
        vehicle,
        period_month,
        ["name", "monthly_litres", "monthly_amount", "consumed_litres", "status"],
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


@frappe.whitelist(allow_guest=True)
@rate_limit(limit=120, seconds=60)
def my_fuel_requests(limit=30):
    """The current driver's OWN fuel-request history (read).

	Identity-scoped via endpoint-scoped ``get_all`` (the ``my_trips_today`` precedent):
	the driver is resolved credential-first and every row is filtered on that driver,
	so this can only return the caller's own requests — the client never supplies a
	driver id. The Driver role holds no read DocPerm on Fuel Request by design (it is a
	staff/oversight-read DocType); the endpoint itself is the authorization boundary, so
	no Driver if_owner DocPerm is added (see the read-access decision on this endpoint).

	Each row carries the request date, requested litres, status, and the Fuel Platform's
	display label (link id swapped for ``platform_name`` like the trip cards), newest
	first. Read-only, no commit."""
    _require_enabled()
    driver = _resolve_driver()
    limit = _bounded_request_limit(limit)
    rows = frappe.get_all(
        "Fuel Request",
        filters={"driver": driver, "docstatus": ["<", 2]},
        fields=["name", "request_date", "requested_litres", "status", "fuel_platform"],
        order_by="request_date desc, creation desc",
        limit=limit,
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
