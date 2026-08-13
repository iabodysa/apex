"""Session-bound custody, incident, fuel top-up, and complaint services for /fleet."""

import frappe
from frappe import _

from apex.salis.api import fleet_employee as base
from apex.salis.utils import add_timeline_note, lock_vehicle, period_quota


def _handover_checklist_template(vehicle, requested_template=None):
    """Return the active native checklist applicable to ``vehicle``."""
    vehicle_category = frappe.db.get_value("Salis Vehicle", vehicle, "vehicle_category")
    if requested_template:
        template = frappe.get_doc("Vehicle Handover Checklist Template", requested_template)
        return _validate_handover_template(template, vehicle_category)

    names = []
    if vehicle_category:
        names = frappe.get_list(
            "Vehicle Handover Checklist Template",
            filters={"is_active": 1, "vehicle_category": vehicle_category},
            pluck="name",
            order_by="template_name asc",
            limit_page_length=1,
        )
    if not names:
        names = frappe.get_list(
            "Vehicle Handover Checklist Template",
            filters={"is_active": 1, "vehicle_category": ["is", "not set"]},
            pluck="name",
            order_by="template_name asc",
            limit_page_length=1,
        )
    if not names:
        frappe.throw(_("No active vehicle handover checklist is configured."))
    return _validate_handover_template(
        frappe.get_doc("Vehicle Handover Checklist Template", names[0]),
        vehicle_category,
    )


def _validate_handover_template(template, vehicle_category):
    if not frappe.has_permission(
        "Vehicle Handover Checklist Template", "read", doc=template
    ):
        frappe.throw(_("You cannot read that handover checklist."), frappe.PermissionError)
    if not template.is_active:
        frappe.throw(_("Checklist template {0} is not active.").format(template.name))
    if template.vehicle_category and template.vehicle_category != vehicle_category:
        frappe.throw(
            _("Checklist template {0} does not apply to this vehicle.").format(
                template.name
            )
        )
    if not template.items:
        frappe.throw(_("The selected handover checklist has no inspection items."))
    return template


def _inspection_rows(template, value):
    """Bind explicit portal answers to every native template row in order."""
    if isinstance(value, str):
        value = frappe.parse_json(value)
    if not isinstance(value, list):
        frappe.throw(_("Inspection answers must be a list."))
    if len(value) != len(template.items):
        frappe.throw(_("Answer every item in the selected handover checklist."))

    result = []
    for template_item, answer in zip(template.items, value, strict=True):
        if not isinstance(answer, dict) or answer.get("check_item") != template_item.check_item:
            frappe.throw(_("Inspection answers do not match the selected checklist template."))
        if "ok" not in answer or answer.get("ok") not in (0, 1, "0", "1", False, True):
            frappe.throw(_("Record a pass or failure for every checklist item."))
        ok = frappe.utils.cint(answer.get("ok"))
        remark = frappe.utils.cstr(answer.get("remark")).strip()
        if not ok and not remark:
            frappe.throw(_("Explain the failed check: {0}.").format(template_item.check_item))
        result.append({"check_item": template_item.check_item, "ok": ok, "remark": remark})
    return result


def _owned_evidence_file(file_url):
    """Lock and return the caller-owned private File used as signed evidence."""
    if not file_url:
        frappe.throw(_("Receipt evidence is required."))
    evidence = frappe.db.get_value(
        "File",
        {
            "file_url": file_url,
            "owner": frappe.session.user,
            "is_private": 1,
        },
        ["name", "attached_to_doctype", "attached_to_name"],
        as_dict=True,
        for_update=True,
    )
    if not evidence:
        frappe.throw(
            _("Signed evidence must be a private file uploaded by your account."),
            frappe.PermissionError,
        )
    return evidence


def _handover_payload(direction, driver, vehicle, odometer, fuel_level=None,
                      condition_notes=None, signed_evidence=None,
                      checklist_template=None, inspection_rows=None):
    payload = {
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
    if checklist_template:
        payload.update({
            "checklist_template": checklist_template.name,
            "handover_check_items": _inspection_rows(checklist_template, inspection_rows),
        })
    return payload


def _submit_session_handover(direction, odometer, fuel_level=None,
                             condition_notes=None, signed_evidence=None,
                             checklist_template=None, inspection_rows=None):
    driver = base._session_driver(required=True)
    vehicle = base._session_vehicle(driver)
    if not vehicle:
        frappe.throw(_("No vehicle is assigned to you."))
    lock_vehicle(vehicle)
    evidence = _owned_evidence_file(signed_evidence)
    template = _handover_checklist_template(vehicle, checklist_template)
    answers = _inspection_rows(template, inspection_rows)
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
    if evidence.attached_to_doctype or evidence.attached_to_name:
        frappe.throw(_("Signed evidence is already attached to another document."))
    doc = frappe.get_doc(
        _handover_payload(
            direction, driver, vehicle, odometer, fuel_level, condition_notes,
            signed_evidence, template, answers
        )
    )
    doc.insert(ignore_permissions=True)
    doc.submit()
    frappe.db.set_value(
        "File",
        evidence.name,
        {
            "attached_to_doctype": "Vehicle Handover",
            "attached_to_name": doc.name,
            "attached_to_field": "signed_evidence",
        },
    )
    return {"name": doc.name, "status": getattr(doc, "status", None) or "Submitted"}


@frappe.whitelist(methods=["POST"])
def receive_vehicle(odometer, fuel_level=None, condition_notes=None, signed_evidence=None,
                    checklist_template=None, inspection_rows=None):
    return _submit_session_handover(
        "Receipt", odometer, fuel_level, condition_notes, signed_evidence,
        checklist_template, inspection_rows
    )


@frappe.whitelist(methods=["POST"])
def return_vehicle(odometer, fuel_level=None, condition_notes=None, signed_evidence=None,
                   checklist_template=None, inspection_rows=None):
    return _submit_session_handover(
        "Return", odometer, fuel_level, condition_notes, signed_evidence,
        checklist_template, inspection_rows
    )


@frappe.whitelist()
def get_handover_checklist(direction):
    """Load the native inspection rows for a session-bound receipt or return."""
    if direction not in ("Receipt", "Return"):
        frappe.throw(_("Direction must be Receipt or Return."))
    driver = base._session_driver(required=True)
    vehicle = base._session_vehicle(driver)
    if not vehicle:
        frappe.throw(_("No vehicle is assigned to you."))
    template = _handover_checklist_template(vehicle)
    return {
        "direction": direction,
        "vehicle": vehicle,
        "template": template.name,
        "items": [
            {"check_item": item.check_item, "default_remark": item.remark or ""}
            for item in template.items
        ],
    }


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
