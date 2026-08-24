# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.workflow import apply_workflow, get_transitions
from frappe.utils import date_diff, flt, today

from apex.apex_core.doctype.salis_settings.salis_settings import get_salis_float
from apex.salis.api.dispatch_board import _permitted_projects
from apex.salis.api.enrich import vehicle_driver_titles


def _drive_fuel_action(doc, action: str) -> None:
    available = {t.action for t in get_transitions(doc)}
    if action in available:
        apply_workflow(doc, action)
        return

    if doc.get("requested_by") == frappe.session.user:
        frappe.throw(
            _("You cannot {0} a fuel request you raised yourself (segregation of duties).").format(
                action.lower()
            ),
            frappe.PermissionError,
        )
    frappe.throw(
        _("Only a Fleet Supervisor, Fleet Project Manager or Fleet Manager can {0} a fuel request.").format(
            action.lower()
        ),
        frappe.PermissionError,
    )


def _approval_threshold() -> float:
    return get_salis_float("fuel_request_approval_threshold_litres", 0.0)


@frappe.whitelist()
def get_pending_fuel_requests(project: str | None = None) -> list[dict]:
    frappe.has_permission("Fuel Request", "read", throw=True)

    unscoped, projects = _permitted_projects()

    if project:
        if unscoped:
            projects = [project]
            unscoped = False
        elif project in (projects or []):
            projects = [project]
        else:
            return []

    if not unscoped and not projects:
        return []

    filters: dict = {"status": "Pending", "docstatus": 0}
    if not unscoped:
        filters["project"] = ["in", projects]

    rows = frappe.get_list(
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
            "request_type",
            "requested_litres",
            "topup_litres",
            "amount",
            "status",
            "requested_by",
        ],
        order_by="request_date desc, modified desc",
        limit_page_length=0,
    )
    if not rows:
        return []

    vehicle_driver_titles(rows)

    threshold = _approval_threshold()
    approval_roles = {"Fleet Supervisor", "Fleet Project Manager", "Fleet Manager", "System Manager"}
    can_workflow = bool(approval_roles.intersection(frappe.get_roles())) and bool(
        frappe.has_permission("Fuel Request", "write")
    )

    result = []
    for r in rows:
        litres = flt(r.topup_litres if r.request_type == "Top-up" else r.requested_litres)
        age_days = date_diff(today(), r.request_date) if r.request_date else None
        result.append(
            {
                "name": r.name,
                "vehicle": r.vehicle,
                "vehicle_plate": r.get("vehicle_plate"),
                "driver": r.driver,
                "driver_name": r.get("driver_name"),
                "project": r.project,
                "fuel_platform": r.fuel_platform,
                "fuel_quota": r.fuel_quota,
                "request_date": str(r.request_date) if r.request_date else None,
                "age_days": age_days,
                "requested_litres": litres,
                "topup_litres": flt(r.topup_litres),
                "request_type": r.request_type,
                "amount": flt(r.amount),
                "status": r.status,
                "over_threshold": bool(threshold and litres > threshold),
                "threshold_litres": threshold,
                "capabilities": {
                    "approve": {
                        "allowed": can_workflow and r.requested_by != frappe.session.user,
                        "reason": _("The requester cannot approve the same request.")
                        if r.requested_by == frappe.session.user
                        else (_("You do not have the approval role.") if not can_workflow else ""),
                    },
                    "reject": {
                        "allowed": can_workflow and r.requested_by != frappe.session.user,
                        "reason": _("The requester cannot reject the same request.")
                        if r.requested_by == frappe.session.user
                        else (_("You do not have the approval role.") if not can_workflow else ""),
                    },
                },
            }
        )
    return result


@frappe.whitelist(methods=["POST"])
def approve_fuel_request(name: str) -> dict:
    doc = frappe.get_doc("Fuel Request", name)
    frappe.has_permission("Fuel Request", "write", doc=doc, throw=True)

    if doc.status != "Pending":
        frappe.throw(
            _("Fuel Request {0} is not pending (current status: {1}).").format(
                name, _(doc.status)
            )
        )

    _drive_fuel_action(doc, "Approve")

    return {"name": doc.name, "status": doc.status}


@frappe.whitelist(methods=["POST"])
def reject_fuel_request(name: str, reason: str | None = None) -> dict:
    doc = frappe.get_doc("Fuel Request", name)
    frappe.has_permission("Fuel Request", "write", doc=doc, throw=True)

    if doc.status != "Pending":
        frappe.throw(
            _("Fuel Request {0} is not pending (current status: {1}).").format(
                name, _(doc.status)
            )
        )

    _drive_fuel_action(doc, "Reject")

    if reason:
        doc.add_comment("Comment", _("Rejected: {0}").format(reason))

    return {"name": doc.name, "status": doc.status}
