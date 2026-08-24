# Copyright (c) 2026, afmcoltd

"""Bring existing records onto the v2.6 state contracts.

The writes pass ``ignore_permissions`` because a patch is migrate context: it runs once as
Administrator with no session user, over records that already exist and whose original author may
no longer have a role. A DocPerm that made these legal would stay live afterwards for everyone.
"""

from __future__ import annotations

import frappe
from frappe.desk.form.assign_to import add as add_assignment
from frappe.desk.form.assign_to import close_all_assignments
from frappe.utils import today

from apex.habitat.doctype.audit_remediation_plan.audit_remediation_plan import (
    derive_overall_status,
)
from apex.habitat.doctype.building_license.building_license import derive_license_status

def driver_status(status):
    if status in (None, "", "On Leave"):
        return "Stopped"
    if status in ("Active", "Stopped", "Released"):
        return status
    raise ValueError(f"Unexpected Salis Driver status: {status!r}")

def maintenance_status(status):
    if status in (None, "", "Assigned", "Reopened"):
        return "Open"
    if status in ("Open", "In Progress", "Resolved", "Closed"):
        return status
    raise ValueError(f"Unexpected Maintenance Request status: {status!r}")

def incident_status(status, docstatus):
    if docstatus not in (0, 1, 2):
        raise ValueError(f"Unexpected Vehicle Incident docstatus: {docstatus!r}")
    if status not in (None, "", "Open", "Under Review", "Closed", "Cancelled"):
        raise ValueError(f"Unexpected Vehicle Incident status: {status!r}")
    if docstatus == 0:
        return "Open"
    if docstatus == 2:
        return "Closed"
    return "Closed" if status == "Closed" else "Under Review"

def remediation_item_status(status):
    if status in (None, ""):
        return "Open"
    if status in (
        "Open",
        "In Progress",
        "Evidence Submitted",
        "Verified by Client",
        "Rejected by Client",
    ):
        return status
    raise ValueError(f"Unexpected Audit Remediation Item status: {status!r}")

def execute():
    _preflight()
    _converge_rows()

def _preflight():
    for status in frappe.get_all("Salis Driver", pluck="status"):
        driver_status(status)

    for row in frappe.get_all(
        "Maintenance Request", fields=["name", "status", "docstatus", "assigned_to"]
    ):
        maintenance_status(row.status)
        if row.assigned_to and not frappe.db.exists("User", {"name": row.assigned_to}):
            raise ValueError(
                f"Maintenance Request {row.name} has unknown assignee {row.assigned_to!r}"
            )

    for row in frappe.get_all(
        "Vehicle Incident", fields=["name", "status", "docstatus"]
    ):
        incident_status(row.status, row.docstatus)

    license_states = {
        None,
        "",
        "Active",
        "Expiring Soon",
        "Expired",
        "Under Renewal",
        "Revoked",
    }
    for row in frappe.get_all(
        "Building License",
        fields=["name", "status", "expiry_date"],
    ):
        if row.status not in license_states:
            raise ValueError(f"Unexpected Building License status: {row.status!r}")
        if row.status != "Revoked" and not row.expiry_date:
            raise ValueError(f"Building License {row.name} has no expiry date")

    for status in frappe.get_all("Audit Remediation Item", pluck="status"):
        remediation_item_status(status)

    plan_states = {
        None,
        "",
        "Open",
        "In Progress",
        "Evidence Submitted",
        "Closed by Client",
        "Overdue",
    }
    for row in frappe.get_all(
        "Audit Remediation Plan", fields=["name", "overall_status"]
    ):
        if row.overall_status not in plan_states:
            raise ValueError(
                f"Unexpected Audit Remediation Plan status: {row.overall_status!r}"
            )

def _set_status(doctype, name, current, target, fieldname="status"):
    if current != target:
        frappe.db.set_value(
            doctype,
            name,
            fieldname,
            target,
            update_modified=False,
        )

def _converge_rows():
    _converge_drivers()
    _converge_maintenance_requests()
    _converge_vehicle_incidents()
    _converge_building_licenses()
    _converge_audit_plans()
    _retire_assignment_notification()
    _converge_maintenance_kanban()

def _converge_drivers():
    for row in frappe.get_all("Salis Driver", fields=["name", "status"]):
        _set_status("Salis Driver", row.name, row.status, driver_status(row.status))

def _converge_maintenance_requests():
    for row in frappe.get_all(
        "Maintenance Request", fields=["name", "status", "docstatus", "assigned_to"]
    ):
        target = maintenance_status(row.status)
        _set_status(
            "Maintenance Request",
            row.name,
            row.status,
            target,
        )
        _converge_maintenance_assignment(
            row.name, target, row.docstatus, row.assigned_to
        )

def _converge_maintenance_assignment(name, status, docstatus, assigned_to):
    if status == "Closed" or docstatus == 2:
        close_all_assignments("Maintenance Request", name, ignore_permissions=True)
        return
    if not assigned_to:
        return
    if frappe.db.exists(
        "ToDo",
        {
            "reference_type": "Maintenance Request",
            "reference_name": name,
            "allocated_to": assigned_to,
            "status": "Open",
        },
    ):
        return
    add_assignment(
        {
            "doctype": "Maintenance Request",
            "name": name,
            "assign_to": frappe.as_json([assigned_to]),
        },
        ignore_permissions=True,
    )

def _converge_vehicle_incidents():
    for row in frappe.get_all(
        "Vehicle Incident", fields=["name", "status", "docstatus"]
    ):
        _set_status(
            "Vehicle Incident",
            row.name,
            row.status,
            incident_status(row.status, row.docstatus),
        )

def _converge_building_licenses():
    as_of = today()
    default_lead = (
        frappe.db.get_single_value("Habitat Settings", "license_expiry_days_before")
        or 60
    )
    for row in frappe.get_all(
        "Building License",
        fields=["name", "status", "expiry_date", "renewal_lead_days"],
    ):
        if row.status == "Revoked":
            continue
        lead_days = row.renewal_lead_days
        if lead_days is None:
            lead_days = default_lead
        target = derive_license_status(row.expiry_date, lead_days, as_of)
        _set_status("Building License", row.name, row.status, target)

def _converge_audit_plans():
    as_of = today()
    for row in frappe.get_all("Audit Remediation Item", fields=["name", "status"]):
        _set_status(
            "Audit Remediation Item",
            row.name,
            row.status,
            remediation_item_status(row.status),
        )

    for plan in frappe.get_all(
        "Audit Remediation Plan",
        fields=["name", "overall_status", "remediation_deadline"],
    ):
        items = frappe.get_all(
            "Audit Remediation Item",
            filters={
                "parent": plan.name,
                "parenttype": "Audit Remediation Plan",
                "parentfield": "remediation_items",
            },
            fields=["status"],
            order_by="idx asc",
        )
        target = derive_overall_status(items, plan.remediation_deadline, as_of)
        _set_status(
            "Audit Remediation Plan",
            plan.name,
            plan.overall_status,
            target,
            fieldname="overall_status",
        )

def _retire_assignment_notification():
    name = "Habitat - Maintenance Request Assigned"
    if frappe.db.exists("Notification", {"name": name}):
        frappe.delete_doc("Notification", name, ignore_permissions=True, force=True)

def _converge_maintenance_kanban():
    name = "Maintenance Requests"
    if not frappe.db.exists("Kanban Board", {"name": name}):
        return
    board = frappe.get_doc("Kanban Board", name)
    canonical = [
        {
            "column_name": column_name,
            "status": "Active",
            "indicator": indicator,
            "order": "[]",
        }
        for column_name, indicator in (
            ("Open", "Blue"),
            ("In Progress", "Orange"),
            ("Resolved", "Green"),
            ("Closed", "Gray"),
        )
    ]
    current = [
        {key: row.get(key) for key in canonical[0]}
        for row in board.get("columns")
    ]
    if current == canonical:
        return
    board.set("columns", [])
    for column in canonical:
        board.append("columns", column)
    board.save(ignore_permissions=True)
