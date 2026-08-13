from __future__ import annotations

import json

import frappe
from frappe import _


SLA_NAME = "Salis Support SLA"
SLA_PRIORITIES = (
    ("Urgent", 3600, 14400, 0),
    ("High", 7200, 28800, 0),
    ("Medium", 14400, 86400, 1),
    ("Low", 28800, 259200, 0),
)
ISSUE_ROLE_PERMISSIONS = (
    ("Driver", {"read": 1, "create": 1, "if_owner": 1}),
    ("Fleet Manager", {"read": 1, "write": 1}),
    ("Fleet Supervisor", {"read": 1, "write": 1}),
    ("Fleet Project Manager", {"read": 1, "write": 1}),
    ("Finance Manager", {"read": 1}),
    ("Internal Auditor", {"read": 1}),
)


def _parse_workdays(value) -> list[str]:
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return []
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            value = [part.strip() for part in value.split(",")]
    return [str(day).strip() for day in (value or []) if str(day).strip()]


def configure_support_sla(
    *, enabled=False, holiday_list=None, workdays=None, start_time=None, end_time=None
):
    """Create the native Issue SLA only after the operator supplies its site schedule."""
    if not enabled:
        return None
    workdays = _parse_workdays(workdays)
    if not (holiday_list and workdays and start_time and end_time):
        frappe.throw(
            _(
                "Holiday List, workdays, support start time and support end time are required "
                "to enable the Salis support SLA."
            )
        )
    if not frappe.db.exists("Holiday List", holiday_list):
        frappe.throw(_("Holiday List {0} does not exist.").format(holiday_list))
    # Native SLA tracking is the opt-in switch for both newly-created and
    # operator-owned existing SLAs. Keep this before either success path so an
    # existing Salis SLA cannot leave Issue tracking disabled.
    frappe.db.set_single_value("Support Settings", "track_service_level_agreement", 1)
    if frappe.db.exists("Service Level Agreement", {"service_level": SLA_NAME}):
        return frappe.db.get_value(
            "Service Level Agreement", {"service_level": SLA_NAME}, "name"
        )

    doc = frappe.new_doc("Service Level Agreement")
    doc.service_level = SLA_NAME
    doc.document_type = "Issue"
    doc.default_service_level_agreement = 1
    doc.enabled = 1
    doc.apply_sla_for_resolution = 1
    doc.holiday_list = holiday_list
    for priority, response, resolution, is_default in SLA_PRIORITIES:
        if frappe.db.exists("Issue Priority", priority):
            doc.append(
                "priorities",
                {
                    "priority": priority,
                    "response_time": response,
                    "resolution_time": resolution,
                    "default_priority": is_default,
                },
            )
    for day in workdays:
        doc.append(
            "support_and_resolution",
            {"workday": day, "start_time": start_time, "end_time": end_time},
        )
    for status in ("Resolved", "Closed"):
        doc.append("sla_fulfilled_on", {"status": status})
    doc.insert(ignore_permissions=True)
    return doc.name


def grant_issue_role_permissions():
    """Create missing native Custom DocPerm rows without rewriting operator-owned rows."""
    if not frappe.db.exists("DocType", "Issue"):
        return
    from frappe.permissions import add_permission, update_permission_property

    for role, flags in ISSUE_ROLE_PERMISSIONS:
        if not frappe.db.exists("Role", role):
            continue
        if frappe.db.exists(
            "Custom DocPerm", {"parent": "Issue", "role": role, "permlevel": 0}
        ):
            continue
        add_permission("Issue", role, ptype="read", permlevel=0)
        for permission_type, value in flags.items():
            update_permission_property("Issue", role, 0, permission_type, value)
