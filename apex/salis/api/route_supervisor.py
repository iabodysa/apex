# Copyright (c) 2026, AFMCO and contributors
"""Masar Route Supervisor portal API — the whitelisted, permission-scoped backend for
the /masar-supervisor SPA.

The Route Supervisor is the person who dispatches buses: they approve the Route Plan
assigned to them, watch boarding fill up per trip, follow the ordered route
stops, and track their driver live on a map. Every endpoint here is scoped to the
CURRENT user's OWN plans — a plan is "theirs" only when its ``route_supervisor`` field
is the session user. A supervisor can never read or act on another supervisor's plan
(Administrator is the sole bypass, for seeding/verification).

Approval model: Route Plan had no supervisor-approval concept — it is a
Movement *fulfilment* record submitted by the planner (docstatus). This module adds a
``route_supervisor`` (User) assignment plus a ``supervisor_approval`` Select
(Pending/Approved/Rejected) with audit stamps to Route Plan. The decision is NOT a
parallel docstatus workflow: the plan stays submitted; approval is an operational sign-off
the supervisor records here. The state-machine write lives on the controller
(``RoutePlan.set_supervisor_decision``); this module owns the permission + precondition
gate around it.

Live oversight reuses the driver-portal telematics already on Dispatch Trip: the driver
portal's ``push_driver_position`` stamps ``driver_lat`` / ``driver_lng`` /
``driver_position_updated_at`` onto the trip while it is dispatched — the same fields the
worker's live ETA reads — so the supervisor map polls those with no new ingestion path.
Boarding reads the trip's ``boarding_state`` child rows (the live per-worker boarding
flow), falling back to the Transport Request manifest size / Route Plan passenger totals
for the expected headcount before the trip starts.
"""

from __future__ import annotations

import frappe
from frappe import _

# Roles allowed to open the supervisor portal at all. Row-level scope (below) narrows
# every read to the caller's own assigned plans regardless of role.
PORTAL_ROLES = (
    "Fleet Supervisor",
    "Fleet Project Manager",
    "Fleet Manager",
    "System Manager",
)

# A driver position older than this (seconds) is flagged stale so the map can dim the
# marker instead of implying the bus is live where it last pinged.
_POSITION_STALE_SECONDS = 120


# ─────────────────────────────── identity / scope ───────────────────────────────

def _require_portal_role():
    """403 unless the caller holds a supervisor/oversight role. Portal gate only —
    it does not grant access to any specific plan; ``_owned_plan`` does that."""
    user = frappe.session.user
    if user == "Administrator":
        return
    if not (set(frappe.get_roles(user)) & set(PORTAL_ROLES)):
        frappe.throw(_("This portal is for route supervisors."), frappe.PermissionError)


def _is_admin(user=None):
    return (user or frappe.session.user) == "Administrator"


def _owned_plan(name: str) -> dict:
    """The Route Plan ``name`` as a dict ONLY when it belongs to the session user
    (``route_supervisor`` == caller), else fail closed with 403.

    Single row-scope guard shared by every per-plan read and by the approve/reject
    writes, so a supervisor can never reach another supervisor's plan by guessing an id.
    Administrator bypasses the ownership test (seeding/verification) but still gets a
    real row or a not-found error."""
    user = frappe.session.user
    plan = frappe.db.get_value(
        "Route Plan",
        name,
        [
            "name",
            "route_name",
            "project",
            "shift",
            "driver",
            "vehicle",
            "transport_request",
            "route_assignment",
            "total_stops",
            "route_supervisor",
            "supervisor_approval",
            "supervisor_action_by",
            "supervisor_action_on",
            "supervisor_rejection_reason",
            "docstatus",
        ],
        as_dict=True,
    )
    if not plan:
        frappe.throw(_("Route plan not found."), frappe.DoesNotExistError)
    if not _is_admin(user) and plan.get("route_supervisor") != user:
        frappe.throw(_("This route plan is not assigned to you."), frappe.PermissionError)
    return plan


def _owned_trip(dispatch_trip: str) -> dict:
    """The Dispatch Trip as a dict only when its Route Plan is owned by the caller.

    Resolves the trip's ``route_plan`` and runs it through ``_owned_plan`` so trip-level
    reads inherit the exact same row-scope as plan-level reads — one supervisor can never
    read another supervisor's trip boarding or driver position."""
    trip = frappe.db.get_value(
        "Dispatch Trip",
        dispatch_trip,
        [
            "name",
            "route_plan",
            "route_assignment",
            "transport_request",
            "status",
            "trip_date",
            "vehicle",
            "driver",
            "driver_user",
            "driver_lat",
            "driver_lng",
            "driver_position_updated_at",
        ],
        as_dict=True,
    )
    if not trip:
        frappe.throw(_("Trip not found."), frappe.DoesNotExistError)
    _owned_plan(trip.get("route_plan"))  # scope gate; raises if not owned
    return trip


# ─────────────────────────────── label helpers ───────────────────────────────

def _driver_label(driver):
    if not driver:
        return None
    return frappe.db.get_value("Salis Driver", driver, "full_name") or driver


def _vehicle_label(vehicle):
    if not vehicle:
        return None
    return frappe.db.get_value("Salis Vehicle", vehicle, "plate_number") or vehicle


def _active_trip_for_plan(route_plan):
    """The most relevant Dispatch Trip for a plan for the supervisor's dashboard: a
    live/today trip first (Dispatched, then today's), else the latest. None when the
    plan has spawned no trip yet. Read-only."""
    if not route_plan:
        return None
    # Prefer a currently-dispatched trip (driver en route — the live case).
    name = frappe.db.get_value(
        "Dispatch Trip",
        {"route_plan": route_plan, "status": "Dispatched", "docstatus": ["<", 2]},
        "name",
        order_by="trip_date desc, creation desc",
    )
    if name:
        return name
    # Else today's trip, else the latest one.
    name = frappe.db.get_value(
        "Dispatch Trip",
        {"route_plan": route_plan, "trip_date": frappe.utils.today(), "docstatus": ["<", 2]},
        "name",
        order_by="creation desc",
    )
    if name:
        return name
    return frappe.db.get_value(
        "Dispatch Trip",
        {"route_plan": route_plan, "docstatus": ["<", 2]},
        "name",
        order_by="trip_date desc, creation desc",
    )


def _manifest_expected(trip: dict) -> int:
    """Expected headcount for a trip before boarding_state is populated: the linked
    Transport Request's ``worker_count``, else the Route Plan's summed stop passengers.
    Zero when neither is known — the UI then just shows the boarded count."""
    tr = trip.get("transport_request")
    if tr:
        wc = frappe.db.get_value("Transport Request", tr, "worker_count")
        if wc:
            return frappe.utils.cint(wc)
    rp = trip.get("route_plan")
    if rp:
        rows = frappe.get_all(
            "Route Stop",
            filters={"parent": rp, "parenttype": "Route Plan"},
            pluck="passengers",
        )
        total = sum(frappe.utils.cint(p) for p in rows if p)
        if total:
            return total
    return 0


def _boarding_summary(dispatch_trip: str, trip: dict | None = None) -> dict:
    """Boarded / expected + a per-status breakdown for a trip, from its live
    ``boarding_state`` child rows. Expected falls back to the manifest size when boarding
    has not started (no state rows yet), so the progress bar reads "0 of M" rather than
    "0 of 0". Read-only."""
    states = frappe.get_all(
        "Trip Boarding State",
        filters={"parent": dispatch_trip, "parenttype": "Dispatch Trip"},
        fields=["employee", "status"],
        order_by="idx asc",
    )
    counts = {"Boarded": 0, "Worker Claimed": 0, "Pending": 0, "Driver Rejected": 0, "Absent": 0}
    for s in states:
        st = s.get("status") or "Pending"
        counts[st] = counts.get(st, 0) + 1

    boarded = counts.get("Boarded", 0)
    if states:
        expected = len(states)
    else:
        expected = _manifest_expected(trip or {"transport_request": None, "route_plan": None})

    return {
        "boarded": boarded,
        "expected": expected,
        "claimed": counts.get("Worker Claimed", 0),
        "pending": counts.get("Pending", 0),
        "rejected": counts.get("Driver Rejected", 0),
        "absent": counts.get("Absent", 0),
        "has_manifest": bool(states),
    }


def _pending_first(plans: list) -> list:
    """Order plans Pending-first, keeping the query's ``modified desc`` inside each group.

    Ordered in PYTHON, not SQL: ``DatabaseQuery.validate_order_by_and_group_by`` rejects
    every order_by function outside frappe's ``ALLOWED_ORDER_BY_FUNCTIONS`` allowlist, and
    ``field()`` is not on it — the old ``field(supervisor_approval,'Pending') desc`` raised
    ValidationError (HTTP 417) on every request, on any dataset. ``sort`` is stable, so the
    SQL order survives within each group, and an unset approval counts as Pending here
    exactly as it does in the payload."""
    plans.sort(key=lambda p: (p.get("supervisor_approval") or "Pending") != "Pending")
    return plans


# ─────────────────────────────── read endpoints ───────────────────────────────

@frappe.whitelist()
def get_supervisor_context():
    """One composite payload for the supervisor portal (read).

    Returns the caller's identity plus every Route Plan assigned to them (submitted
    plans — a draft plan is not yet handed to a supervisor), Pending decisions first, each
    enriched with human driver/vehicle labels and its most-relevant Dispatch Trip's live
    boarding summary + whether a live driver position exists. Strictly row-scoped: only
    plans where ``route_supervisor`` == the session user (Administrator sees all, for
    verification). Read-only, no commit."""
    _require_portal_role()
    user = frappe.session.user

    filters = {"docstatus": 1}
    if not _is_admin(user):
        filters["route_supervisor"] = user

    plans = frappe.get_all(
        "Route Plan",
        filters=filters,
        fields=[
            "name",
            "route_name",
            "project",
            "shift",
            "driver",
            "vehicle",
            "transport_request",
            "route_assignment",
            "total_stops",
            "route_supervisor",
            "supervisor_approval",
            "supervisor_action_on",
            "supervisor_rejection_reason",
            "modified",
        ],
        order_by="modified desc",
        limit_page_length=0,
    )
    plans = _pending_first(plans)

    out = []
    for p in plans:
        trip_name = _active_trip_for_plan(p["name"])
        trip_block = None
        if trip_name:
            t = frappe.db.get_value(
                "Dispatch Trip",
                trip_name,
                ["name", "status", "trip_date", "route_plan", "transport_request",
                 "driver_lat", "driver_lng", "driver_position_updated_at"],
                as_dict=True,
            )
            summary = _boarding_summary(trip_name, t)
            trip_block = {
                "name": t["name"],
                "status": t.get("status"),
                "trip_date": frappe.utils.cstr(t.get("trip_date")) if t.get("trip_date") else None,
                "boarding": summary,
                "has_position": t.get("driver_lat") is not None and t.get("driver_lng") is not None,
            }
        out.append(
            {
                "name": p["name"],
                "route_name": p.get("route_name"),
                "project": p.get("project"),
                "shift": p.get("shift"),
                "driver": _driver_label(p.get("driver")),
                "vehicle": _vehicle_label(p.get("vehicle")),
                "total_stops": frappe.utils.cint(p.get("total_stops")),
                "approval": p.get("supervisor_approval") or "Pending",
                "decided_on": frappe.utils.cstr(p.get("supervisor_action_on"))
                if p.get("supervisor_action_on")
                else None,
                "rejection_reason": p.get("supervisor_rejection_reason"),
                "trip": trip_block,
            }
        )

    pending = sum(1 for p in out if p["approval"] == "Pending")
    return {
        "supervisor": {
            "user": user,
            "full_name": frappe.utils.get_fullname(user) or user,
        },
        "counts": {"total": len(out), "pending": pending},
        "plans": out,
        "generated_at": frappe.utils.cstr(frappe.utils.now_datetime()),
    }


@frappe.whitelist()
def get_route_stops(route_plan: str):
    """The ordered stops of a plan the caller owns (read).

    Reuses masar's read-only ``_ordered_stops`` so the sequence, planned times, expected
    passengers and Habitat pickup enrichment are identical to what the driver and worker
    apps render. Row-scoped via ``_owned_plan``."""
    _require_portal_role()
    plan = _owned_plan(route_plan)

    from apex.salis.api import masar

    stops = masar._ordered_stops(route_plan)
    return {
        "route_plan": route_plan,
        "route_name": plan.get("route_name"),
        "total_stops": len(stops),
        "stops": stops,
    }


@frappe.whitelist()
def get_trip_boarding(dispatch_trip: str):
    """Live boarding for a trip the caller owns: boarded vs expected plus the
    per-worker boarding state (read).

    Reads the trip's ``boarding_state`` child rows (the live boarding flow's per-worker
    ledger) and resolves each worker's display name. Expected falls back to the manifest
    size before boarding starts. Row-scoped via ``_owned_trip``."""
    _require_portal_role()
    trip = _owned_trip(dispatch_trip)
    summary = _boarding_summary(dispatch_trip, trip)

    rows = frappe.get_all(
        "Trip Boarding State",
        filters={"parent": dispatch_trip, "parenttype": "Dispatch Trip"},
        fields=["employee", "status", "confirm_source", "worker_claim_at"],
        order_by="idx asc",
    )
    emp_names = {}
    ids = [r["employee"] for r in rows if r.get("employee")]
    if ids:
        for e in frappe.get_all(
            "Employee", filters={"name": ["in", ids]}, fields=["name", "employee_name"]
        ):
            emp_names[e["name"]] = e.get("employee_name")
    workers = [
        {
            "employee": r.get("employee"),
            "employee_name": emp_names.get(r.get("employee")) or r.get("employee"),
            "status": r.get("status") or "Pending",
            "confirm_source": r.get("confirm_source"),
        }
        for r in rows
    ]

    return {
        "dispatch_trip": dispatch_trip,
        "status": trip.get("status"),
        "trip_date": frappe.utils.cstr(trip.get("trip_date")) if trip.get("trip_date") else None,
        "boarding": summary,
        "workers": workers,
    }


@frappe.whitelist()
def get_trip_driver_position(dispatch_trip: str):
    """The live driver GPS position for a trip the caller owns (read).

    Returns the last position the driver portal stamped on the Dispatch Trip
    (``driver_lat`` / ``driver_lng`` / ``driver_position_updated_at``) plus a computed
    ``age_seconds`` and ``stale`` flag so the map can dim an out-of-date marker.
    ``has_position`` is False when the driver has not pushed a fix yet — the client then
    shows the graceful "no live position" state instead of a marker at (0,0). Row-scoped
    via ``_owned_trip``."""
    _require_portal_role()
    trip = _owned_trip(dispatch_trip)

    lat = trip.get("driver_lat")
    lng = trip.get("driver_lng")
    updated = trip.get("driver_position_updated_at")
    has_position = lat is not None and lng is not None and (lat or lng)

    age_seconds = None
    stale = None
    if updated:
        age_seconds = int(frappe.utils.time_diff_in_seconds(frappe.utils.now_datetime(), updated))
        stale = age_seconds > _POSITION_STALE_SECONDS

    return {
        "dispatch_trip": dispatch_trip,
        "status": trip.get("status"),
        "has_position": bool(has_position),
        "lat": lat,
        "lng": lng,
        "updated_at": frappe.utils.cstr(updated) if updated else None,
        "age_seconds": age_seconds,
        "stale": stale,
        "driver": trip.get("driver"),
        "driver_name": _driver_label(trip.get("driver")),
        "vehicle": trip.get("vehicle"),
        "plate": _vehicle_label(trip.get("vehicle")),
    }


# ─────────────────────────────── write endpoints ───────────────────────────────

def _resolve_owned_plan_doc(name: str):
    """Load the Route Plan doc for a decision write, enforcing the same ownership +
    lifecycle preconditions for both approve and reject: the caller must be the assigned
    supervisor (Administrator bypass), the plan must be submitted, and no decision may
    have been recorded yet (idempotent — a decided plan cannot be re-decided).

    The existence probe filters on ``name``: the positional form answers the value
    back without querying when it equals the DocType (database.py:1259), so the
    literal "Route Plan" cleared the not-found throw and fell through to the
    ownership branch — a supervisor-mismatch error, or a bare 404 for an admin."""
    user = frappe.session.user
    supervisor = frappe.db.get_value("Route Plan", name, "route_supervisor")
    if supervisor is None and not frappe.db.exists("Route Plan", {"name": name}):
        frappe.throw(_("Route plan not found."), frappe.DoesNotExistError)
    if not _is_admin(user) and supervisor != user:
        frappe.throw(_("This route plan is not assigned to you."), frappe.PermissionError)

    doc = frappe.get_doc("Route Plan", name)
    if doc.docstatus != 1:
        frappe.throw(_("Only a submitted route plan can be approved or rejected."))
    if (doc.supervisor_approval or "Pending") != "Pending":
        frappe.throw(
            _("This plan has already been {0}.").format(_(doc.supervisor_approval))
        )
    return doc


def _decision_result(doc) -> dict:
    return {
        "name": doc.name,
        "approval": doc.supervisor_approval,
        "decided_by": doc.supervisor_action_by,
        "decided_on": frappe.utils.cstr(doc.supervisor_action_on)
        if doc.supervisor_action_on
        else None,
        "rejection_reason": doc.supervisor_rejection_reason,
    }


@frappe.whitelist(methods=["POST"])
def approve_route_plan(name: str):
    """Approve a Route Plan assigned to the caller (write).

    Guarded by ``_resolve_owned_plan_doc``: only the assigned supervisor may act
    (Administrator bypass), only a submitted plan, and only while still Pending. Records
    ``supervisor_approval = Approved`` with audit stamps via the controller state-writer.
    No GL — this is an operational sign-off, not a ledger posting."""
    _require_portal_role()
    doc = _resolve_owned_plan_doc(name)
    doc.set_supervisor_decision("Approved", frappe.session.user)
    return _decision_result(doc)


@frappe.whitelist(methods=["POST"])
def reject_route_plan(name: str, reason: str):
    """Reject a Route Plan assigned to the caller, with a reason (write).

    Same ownership + lifecycle guard as approve; additionally requires a non-empty reason
    (the rejection is actionable feedback to the planner). Records
    ``supervisor_approval = Rejected`` + the reason via the controller state-writer."""
    _require_portal_role()
    reason = (reason or "").strip()
    if not reason:
        frappe.throw(_("A rejection reason is required."))
    doc = _resolve_owned_plan_doc(name)
    doc.set_supervisor_decision("Rejected", frappe.session.user, reason)
    return _decision_result(doc)
