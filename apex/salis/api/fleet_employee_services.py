"""Session-bound custody, incident, fuel top-up, and complaint services for /fleet."""

import frappe
from frappe import _

from apex.salis.api import fleet_employee as base
from apex.salis.utils import add_timeline_note, period_quota


def _handover_payload(direction, driver, vehicle, odometer, fuel_level=None,
                      condition_notes=None, signed_evidence=None):
    return {
        "doctype": "Vehicle Handover",
        "direction": direction,
        "vehicle": vehicle,
        "from_driver": driver if direction in ("Transfer", "Return") else None,
        "to_driver": driver if direction == "Receipt" else None,
        "handover_date": frappe.utils.today(),
        "odometer_reading": frappe.utils.cint(odometer),
        "fuel_level": fuel_level or None,
        "condition_notes": (condition_notes or "").strip(),
        "signed_evidence": signed_evidence or None,
        "discrepancy_status": "Clean",
    }


def _submit_session_handover(direction, odometer, fuel_level=None,
                             condition_notes=None, signed_evidence=None):
    driver = base._session_driver(required=True)
    vehicle = base._session_vehicle(driver)
    if not vehicle:
        frappe.throw(_("No vehicle is assigned to you."))
    if not signed_evidence:
        frappe.throw(_("Receipt evidence is required."))
    duplicate = frappe.db.get_value(
        "Vehicle Handover",
        {
            "direction": direction,
            "vehicle": vehicle,
            "from_driver": driver if direction == "Return" else ["is", "not set"],
            "to_driver": driver if direction == "Receipt" else ["is", "not set"],
            "signed_evidence": signed_evidence,
            "docstatus": 1,
        },
        "name",
    )
    if duplicate:
        return {"name": duplicate, "status": "Submitted"}
    doc = frappe.get_doc(
        _handover_payload(
            direction, driver, vehicle, odometer, fuel_level, condition_notes, signed_evidence
        )
    )
    doc.insert(ignore_permissions=True)
    doc.submit()
    return {"name": doc.name, "status": getattr(doc, "status", None) or "Submitted"}


@frappe.whitelist(methods=["POST"])
def receive_vehicle(odometer, fuel_level=None, condition_notes=None, signed_evidence=None):
    return _submit_session_handover(
        "Receipt", odometer, fuel_level, condition_notes, signed_evidence
    )


@frappe.whitelist(methods=["POST"])
def return_vehicle(odometer, fuel_level=None, condition_notes=None, signed_evidence=None):
    return _submit_session_handover(
        "Return", odometer, fuel_level, condition_notes, signed_evidence
    )


@frappe.whitelist()
def get_my_handovers(limit=30):
    driver = base._session_driver()
    if not driver:
        return []
    return frappe.get_list(
        "Vehicle Handover",
        filters={"docstatus": ["<", 2]},
        or_filters={"from_driver": driver, "to_driver": driver},
        fields=[
            "name", "direction", "vehicle", "handover_date", "odometer_reading",
            "discrepancy_status", "docstatus",
        ],
        order_by="handover_date desc, creation desc",
        limit_page_length=min(max(frappe.utils.cint(limit) or 30, 1), 100),
    )


@frappe.whitelist()
def get_my_fuel_quota():
    driver = base._session_driver()
    vehicle = base._session_vehicle(driver)
    quota = period_quota(vehicle, frappe.utils.today()[:7], [
        "name", "monthly_litres", "consumed_litres", "status", "period_month"
    ]) if vehicle else None
    if not quota:
        return {"quota": None}
    monthly = frappe.utils.flt(quota.monthly_litres)
    consumed = frappe.utils.flt(quota.consumed_litres)
    return {"quota": {
        "name": quota.name,
        "period_month": quota.period_month,
        "monthly_litres": monthly,
        "consumed_litres": consumed,
        "remaining_litres": max(monthly - consumed, 0),
        "status": quota.status,
    }}


@frappe.whitelist(methods=["POST"])
def submit_additional_fuel_request(topup_litres, reason):
    driver = base._session_driver(required=True)
    vehicle = base._session_vehicle(driver)
    if not vehicle:
        frappe.throw(_("No vehicle is assigned to you."))
    litres = frappe.utils.flt(topup_litres)
    if litres <= 0:
        frappe.throw(_("Top-up Litres must be greater than zero."))
    reason = frappe.utils.cstr(reason).strip()
    if not reason:
        frappe.throw(_("Enter the reason for the additional fuel request."))
    quota = period_quota(vehicle, frappe.utils.today()[:7], ["name"])
    doc = frappe.get_doc({
        "doctype": "Fuel Request",
        "request_type": "Top-up",
        "vehicle": vehicle,
        "driver": driver,
        "project": base._driver_project(driver),
        "fuel_quota": quota.name if quota else None,
        "topup_litres": litres,
        "request_date": frappe.utils.today(),
        "status": "Pending",
    })
    doc.insert(ignore_permissions=True)
    add_timeline_note("Fuel Request", doc.name, _("Reason: {0}").format(reason))
    return {"name": doc.name, "status": doc.status}


@frappe.whitelist()
def get_my_incidents(limit=50):
    driver = base._session_driver()
    if not driver:
        return []
    return frappe.get_list(
        "Vehicle Incident",
        filters={"driver": driver, "docstatus": ["<", 2]},
        fields=["name", "incident_type", "incident_date", "vehicle", "location", "description", "status"],
        order_by="incident_date desc, creation desc",
        limit_page_length=min(max(frappe.utils.cint(limit) or 50, 1), 100),
    )


@frappe.whitelist(methods=["POST"])
def report_incident(incident_type, incident_date, description, incident_time=None,
                    location=None, odometer_at_incident=None, evidence=None):
    driver = base._session_driver(required=True)
    vehicle = base._session_vehicle(driver)
    if not vehicle:
        frappe.throw(_("No vehicle is assigned to you."))
    doc = frappe.get_doc({
        "doctype": "Vehicle Incident",
        "incident_type": incident_type,
        "vehicle": vehicle,
        "driver": driver,
        "incident_date": incident_date,
        "incident_time": incident_time or None,
        "location": frappe.utils.cstr(location).strip() or None,
        "odometer_at_incident": frappe.utils.cint(odometer_at_incident) or None,
        "description": frappe.utils.cstr(description).strip(),
        "evidence": evidence or None,
        "reported_by": frappe.session.user,
        "status": "Open",
    })
    doc.insert(ignore_permissions=True)
    return {"name": doc.name, "status": doc.status}


def _my_issue(name=None):
    driver = base._session_driver(required=True)
    filters = {"custom_driver": driver, "issue_type": "Complaint"}
    if name:
        filters["name"] = name
    rows = frappe.get_list(
        "Issue", filters=filters,
        fields=["name", "subject", "description", "status", "priority", "creation", "modified"],
        order_by="modified desc", limit_page_length=1 if name else 50,
    )
    if name and not rows:
        frappe.throw(_("Complaint not found."), frappe.DoesNotExistError)
    return rows


@frappe.whitelist()
def get_my_complaints():
    return _my_issue()


@frappe.whitelist()
def get_complaint(name):
    issue = _my_issue(name)[0]
    issue["communications"] = frappe.get_all(
        "Communication",
        filters={"reference_doctype": "Issue", "reference_name": name},
        fields=["name", "sender", "content", "communication_date"],
        order_by="communication_date asc, creation asc",
        limit_page_length=100,
    )
    for item in issue["communications"]:
        item["content"] = frappe.utils.strip_html_tags(item.get("content") or "").strip()
    return issue


@frappe.whitelist(methods=["POST"])
def create_complaint(priority, subject, description, attachment=None):
    driver = base._session_driver(required=True)
    subject = frappe.utils.cstr(subject).strip()
    description = frappe.utils.cstr(description).strip()
    if not subject or not description:
        frappe.throw(_("Subject and description are required."))
    doc = frappe.get_doc({
        "doctype": "Issue",
        "issue_type": "Complaint",
        "priority": priority or "Medium",
        "subject": subject,
        "description": description,
        "custom_driver": driver,
        "project": base._driver_project(driver),
        "raised_by": frappe.session.user,
        "via_customer_portal": 1,
        "status": "Open",
    })
    doc.insert(ignore_permissions=True)
    if attachment:
        file_name = frappe.db.get_value(
            "File", {"file_url": attachment, "owner": frappe.session.user, "is_private": 1}, "name"
        )
        if file_name:
            frappe.db.set_value(
                "File", file_name,
                {"attached_to_doctype": "Issue", "attached_to_name": doc.name},
            )
    return {"name": doc.name, "status": doc.status}


@frappe.whitelist(methods=["POST"])
def reply_to_complaint(name, message):
    issue = _my_issue(name)[0]
    message = frappe.utils.cstr(message).strip()
    if not message:
        frappe.throw(_("Enter a reply."))
    communication = frappe.get_doc({
        "doctype": "Communication",
        "communication_type": "Communication",
        "communication_medium": "Other",
        "sent_or_received": "Sent",
        "sender": frappe.session.user,
        "content": message,
        "reference_doctype": "Issue",
        "reference_name": name,
    })
    communication.insert(ignore_permissions=True)
    if issue.status in ("Resolved", "Closed"):
        frappe.db.set_value("Issue", name, "status", "Open")
    status = "Open" if issue.status in ("Resolved", "Closed") else issue.status
    return {"name": communication.name, "status": status}
