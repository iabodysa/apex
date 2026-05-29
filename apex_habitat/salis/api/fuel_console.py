"""Fuel Approval Console API (Salis).

A thin presentation + orchestration layer over the Fuel Request controller,
mirroring the Habitat Front Desk pattern:

- ``get_pending_fuel_requests`` is read-only and built from a single bounded
  query (no N+1). It returns submitted Fuel Requests still in ``Pending``
  status together with the joined vehicle plate and driver name, plus an
  ``over_threshold`` flag computed against
  ``Salis Settings.fuel_request_approval_threshold_litres``.
- ``approve_fuel_request`` / ``reject_fuel_request`` load the real Fuel Request
  document and mutate it through ``doc.save()`` so all native controller
  behavior runs. They add NO posting or status logic of their own beyond the
  documented field updates, and they never touch the database with raw SQL.

Every write is permission-gated on ``Fuel Request`` / ``write`` (defense in
depth on top of the page role grant). The approve/reject mutations run through
``doc.save()``, so the change is captured natively by Version (track_changes is
enabled on Fuel Request) plus the automatic timeline comment.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import date_diff, flt, today


def _approval_threshold() -> float:
    """Litre threshold above which a Fuel Request needs explicit approval.

    Read from the Salis Settings single. Returns 0.0 when unset (no threshold).
    """
    value = frappe.db.get_single_value(
        "Salis Settings", "fuel_request_approval_threshold_litres"
    )
    return flt(value)


@frappe.whitelist()
def get_pending_fuel_requests(project: str | None = None) -> list[dict]:
    """Return submitted Fuel Requests awaiting approval (status == Pending).

    Read-only. Permission-gated on ``Fuel Request`` / ``read``. Built from a
    single ORM query with the vehicle plate and driver name resolved via
    ``Salis Vehicle`` / ``Salis Driver`` title lookups in bounded bulk reads
    (no per-row round trips). Each row carries an ``over_threshold`` flag
    computed against the Salis Settings approval threshold.

    Args:
        project: Optional Project docname to filter the queue.

    Returns:
        list of dicts, newest request first.
    """
    frappe.has_permission("Fuel Request", "read", throw=True)

    filters: dict = {"status": "Pending", "docstatus": 1}
    if project:
        filters["project"] = project

    rows = frappe.get_all(
        "Fuel Request",
        filters=filters,
        fields=[
            "name",
            "vehicle",
            "driver",
            "project",
            "fuel_platform",
            "fuel_quota",
            "request_date",
            "requested_litres",
            "amount",
            "status",
        ],
        order_by="request_date desc, modified desc",
        limit_page_length=0,
    )
    if not rows:
        return []

    # Resolve display titles in bounded bulk reads (no N+1).
    vehicle_names = list({r.vehicle for r in rows if r.vehicle})
    driver_names = list({r.driver for r in rows if r.driver})

    plate_by_vehicle: dict = {}
    if vehicle_names:
        for v in frappe.get_all(
            "Salis Vehicle",
            filters={"name": ["in", vehicle_names]},
            fields=["name", "plate_number"],
        ):
            plate_by_vehicle[v.name] = v.get("plate_number")

    name_by_driver: dict = {}
    if driver_names:
        for d in frappe.get_all(
            "Salis Driver",
            filters={"name": ["in", driver_names]},
            fields=["name", "full_name"],
        ):
            name_by_driver[d.name] = d.get("full_name")

    threshold = _approval_threshold()

    result = []
    for r in rows:
        litres = flt(r.requested_litres)
        age_days = date_diff(today(), r.request_date) if r.request_date else None
        result.append(
            {
                "name": r.name,
                "vehicle": r.vehicle,
                "vehicle_plate": plate_by_vehicle.get(r.vehicle) or r.vehicle,
                "driver": r.driver,
                "driver_name": name_by_driver.get(r.driver) or r.driver,
                "project": r.project,
                "fuel_platform": r.fuel_platform,
                "fuel_quota": r.fuel_quota,
                "request_date": str(r.request_date) if r.request_date else None,
                "age_days": age_days,
                "requested_litres": litres,
                "amount": flt(r.amount),
                "status": r.status,
                "over_threshold": bool(threshold and litres > threshold),
                "threshold_litres": threshold,
            }
        )
    return result


@frappe.whitelist(methods=["POST"])
def approve_fuel_request(name: str) -> dict:
    """Approve a Pending Fuel Request.

    Loads the real Fuel Request document, sets ``status = Approved`` and
    ``approved_by = <current user>``, then ``doc.save()`` so native controller
    behavior runs. No raw SQL.

    Permission: caller must have ``write`` on Fuel Request (checked explicitly
    below, defense in depth on top of the page role grant).

    Args:
        name: Fuel Request docname.

    Returns:
        dict: ``{"name": <docname>, "status": "Approved"}``.
    """
    frappe.has_permission("Fuel Request", "write", throw=True)

    doc = frappe.get_doc("Fuel Request", name)
    if doc.status != "Pending":
        frappe.throw(
            _("Fuel Request {0} is not pending (current status: {1}).").format(
                name, _(doc.status)
            )
        )

    doc.status = "Approved"
    doc.approved_by = frappe.session.user
    doc.save()

    # The save above is captured natively by Version (track_changes) + auto-comment.
    return {"name": doc.name, "status": doc.status}


@frappe.whitelist(methods=["POST"])
def reject_fuel_request(name: str, reason: str | None = None) -> dict:
    """Reject a Pending Fuel Request.

    Loads the real Fuel Request document, sets ``status = Failed`` and
    ``approved_by = <current user>``, records the reason as a timeline comment,
    then ``doc.save()``. No raw SQL.

    Permission: caller must have ``write`` on Fuel Request (checked explicitly
    below).

    Args:
        name: Fuel Request docname.
        reason: Optional human-readable rejection reason.

    Returns:
        dict: ``{"name": <docname>, "status": "Failed"}``.
    """
    frappe.has_permission("Fuel Request", "write", throw=True)

    doc = frappe.get_doc("Fuel Request", name)
    if doc.status != "Pending":
        frappe.throw(
            _("Fuel Request {0} is not pending (current status: {1}).").format(
                name, _(doc.status)
            )
        )

    doc.status = "Failed"
    doc.approved_by = frappe.session.user
    doc.save()

    if reason:
        doc.add_comment("Comment", _("Rejected: {0}").format(reason))

    # The save above is captured natively by Version (track_changes) + auto-comment.
    return {"name": doc.name, "status": doc.status}
