"""Fuel Approval Console API (Salis).

A thin presentation + orchestration layer over the Fuel Request controller,
mirroring the Habitat Front Desk pattern:

- ``get_pending_fuel_requests`` is read-only and built from a single bounded
  query (no N+1). It returns submitted Fuel Requests still in ``Pending``
  status together with the joined vehicle plate and driver name, plus an
  ``over_threshold`` flag computed against
  ``Salis Settings.fuel_request_approval_threshold_litres``.
- ``approve_fuel_request`` / ``reject_fuel_request`` load the real Fuel Request
  document and drive the native **Fuel Request Workflow** (the ``Approve`` /
  ``Reject`` transitions) via ``frappe.model.workflow.apply_workflow``, so the
  workflow's role gate, Segregation-of-Duties condition
  (``requested_by != session.user``) and docstatus transition all apply — the
  console can never bypass them. They add NO posting or status logic of their
  own, and never touch the database with raw SQL.

Project scoping is enforced SERVER-SIDE and reuses the canonical Salis row-scope
helpers in :mod:`apex_habitat.salis.permissions` (``_is_unscoped`` /
``_allowed_projects``), exactly like ``salis.api.dispatch_board``: a scoped
supervisor only ever sees Fuel Requests in the projects they hold a User
Permission for, and an out-of-scope ``project`` argument can never widen that
view (it simply yields an empty queue). A scoped user with no permitted project
sees an empty queue (mirroring the ``1=0`` fragment the list-view query
condition applies). Approve/reject additionally run a per-document
``frappe.has_permission("Fuel Request", "write", doc=...)`` so the same project
boundary is enforced on the individual document, not just a blanket write grant.

The approve/reject mutations run through ``doc.save()``, so the change is
captured natively by Version (track_changes is enabled on Fuel Request) plus the
automatic timeline comment.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.workflow import apply_workflow
from frappe.utils import date_diff, flt, today

from apex_habitat.salis.permissions import _allowed_projects, _is_unscoped


def _permitted_projects():
    """Resolve the project scope for the current user.

    Returns a tuple ``(unscoped, projects)`` with the same contract as
    ``dispatch_board._permitted_projects``:

      * ``unscoped`` is True for oversight roles that see every project, in which
        case ``projects`` is ``None`` (no project filter applied);
      * otherwise ``projects`` is the list of Project names the user holds a User
        Permission for. An empty list means the user is scoped but granted no
        project, so the queue must be empty.

    This delegates to the same helpers the ``permission_query_conditions`` hooks
    use, so the console scope and the list-view scope can never diverge.
    """
    user = frappe.session.user
    if _is_unscoped(user):
        return True, None
    return False, _allowed_projects(user)


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
    """Return Fuel Requests awaiting approval (the draft ``Pending`` queue).

    Under the Fuel Request Workflow a request awaiting approval is a draft
    (``Pending`` maps to docstatus 0); the ``Approve`` transition is what submits
    it. The queue therefore lists ``status == Pending`` drafts (docstatus 0).

    Read-only. Permission-gated on ``Fuel Request`` / ``read``. Built from a
    single ORM query with the vehicle plate and driver name resolved via
    ``Salis Vehicle`` / ``Salis Driver`` title lookups in bounded bulk reads
    (no per-row round trips). Each row carries an ``over_threshold`` flag
    computed against the Salis Settings approval threshold.

    Project scoping is enforced server-side: a scoped supervisor only ever sees
    Fuel Requests in their permitted projects. The ``project`` argument can only
    NARROW that scope (it is intersected with the permitted set), never widen it.

    Args:
        project: Optional Project docname to narrow the queue to a single
            project. Intersected with the caller's permitted scope — an
            out-of-scope project yields an empty queue.

    Returns:
        list of dicts, newest request first.
    """
    frappe.has_permission("Fuel Request", "read", throw=True)

    unscoped, projects = _permitted_projects()

    # Intersect an explicitly requested project with the permitted scope. A
    # scoped user must never be able to widen their view via the argument.
    if project:
        if unscoped:
            projects = [project]
            unscoped = False
        elif project in (projects or []):
            projects = [project]
        else:
            # Requested project is outside the caller's scope: empty queue.
            return []

    # Scoped user with no permitted project => empty queue (mirrors `1=0`).
    if not unscoped and not projects:
        return []

    filters: dict = {"status": "Pending", "docstatus": 0}
    if not unscoped:
        filters["project"] = ["in", projects]

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
    """Approve a Pending Fuel Request by driving the workflow ``Approve`` action.

    Loads the real Fuel Request document and applies the native Fuel Request
    Workflow ``Approve`` transition (Pending -> Approved, which submits the
    request). The workflow enforces the role gate and the Segregation-of-Duties
    condition (the approver cannot be the requester); the controller stamps
    ``approved_by`` on entering Approved. No raw SQL.

    Permission: caller must have ``write`` on this specific Fuel Request. The
    per-document check (``doc=doc``) runs the project row-scope ``has_permission``
    hook, so a scoped supervisor cannot approve a request outside their permitted
    projects even though they hold a blanket Fuel Request write grant. The
    workflow transition then applies its own role + SoD gate on top.

    Args:
        name: Fuel Request docname.

    Returns:
        dict: ``{"name": <docname>, "status": "Approved"}``.
    """
    doc = frappe.get_doc("Fuel Request", name)
    frappe.has_permission("Fuel Request", "write", doc=doc, throw=True)

    if doc.status != "Pending":
        frappe.throw(
            _("Fuel Request {0} is not pending (current status: {1}).").format(
                name, _(doc.status)
            )
        )

    apply_workflow(doc, "Approve")

    # The transition is captured natively by Version (track_changes) + the
    # automatic Workflow comment; the controller stamps approved_by.
    return {"name": doc.name, "status": doc.status}


@frappe.whitelist(methods=["POST"])
def reject_fuel_request(name: str, reason: str | None = None) -> dict:
    """Reject a Pending Fuel Request by driving the workflow ``Reject`` action.

    Loads the real Fuel Request document and applies the native Fuel Request
    Workflow ``Reject`` transition (Pending -> Failed). The workflow enforces the
    role gate and the Segregation-of-Duties condition (the reviewer cannot be the
    requester). The reason, if given, is recorded as a timeline comment. No raw
    SQL.

    Permission: caller must have ``write`` on this specific Fuel Request. The
    per-document check (``doc=doc``) runs the project row-scope ``has_permission``
    hook, so a scoped supervisor cannot reject a request outside their permitted
    projects even though they hold a blanket Fuel Request write grant. The
    workflow transition then applies its own role + SoD gate on top.

    Args:
        name: Fuel Request docname.
        reason: Optional human-readable rejection reason.

    Returns:
        dict: ``{"name": <docname>, "status": "Failed"}``.
    """
    doc = frappe.get_doc("Fuel Request", name)
    frappe.has_permission("Fuel Request", "write", doc=doc, throw=True)

    if doc.status != "Pending":
        frappe.throw(
            _("Fuel Request {0} is not pending (current status: {1}).").format(
                name, _(doc.status)
            )
        )

    apply_workflow(doc, "Reject")

    if reason:
        doc.add_comment("Comment", _("Rejected: {0}").format(reason))

    # The transition is captured natively by Version (track_changes) + auto-comment.
    return {"name": doc.name, "status": doc.status}
