# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import re

import frappe
from frappe import _
from frappe.desk.form.assign_to import add as add_assignment
from frappe.desk.form.assign_to import close_all_assignments
from frappe.model.document import Document
from frappe.utils import sha256_hash
from apex.apex_core.utils.party_link import sync_party_employee

class ResidentRequest(Document):
    pass

_CATEGORY_TARGET = {
    "Maintenance": "Maintenance Request",
    "Water": "Maintenance Request",
    "Electrical": "Maintenance Request",
    "AC": "Maintenance Request",
    "Plumbing": "Maintenance Request",
    "Cleaning": "Maintenance Request",
    "Pest Control": "Maintenance Request",
    "Facility Item": "Maintenance Request",
    "Safety": "Safety Incident",
    "Custody": "Custody Issue",
}

_CATEGORY_TO_ISSUE_TYPE = {
    "Maintenance": "Other",
    "Water": "Plumbing",
    "Plumbing": "Plumbing",
    "Electrical": "Electrical",
    "AC": "Air Conditioning",
    "Cleaning": "Other",
    "Pest Control": "Pest Control",
    "Facility Item": "Furniture",
    "Safety": "Fire Safety",
}

def before_insert(doc, method=None):
    if not doc.anonymous_tracking_code:
        doc.anonymous_tracking_code = frappe.generate_hash(length=8).upper()

    if not doc.source_channel:
        doc.source_channel = "QR Web Form"

    if not doc.status:
        doc.status = "New"

    _populate_location_from_token(doc)
    _apply_priority_rules(doc)

def validate(doc, method=None):
    if doc.get("website_field"):
        frappe.throw(_("Invalid submission."), frappe.PermissionError)

    _populate_location_from_token(doc)
    sync_party_employee(doc)
    if doc.location_token and not doc.building:
        frappe.throw(_("Invalid or inactive location token."))

    _validate_status_transition(doc)

def on_update(doc, method=None):
    _sync_assignment_todo(doc)

def _sync_assignment_todo(doc):
    if doc.status in ("Resolved", "Rejected", "Closed"):
        close_all_assignments(doc.doctype, doc.name)
        doc.modified = frappe.db.get_value(doc.doctype, doc.name, "modified")
        return

    if doc.status != "Assigned" or not doc.assigned_to:
        return

    add_assignment({
        "doctype": doc.doctype,
        "name": doc.name,
        "assign_to": frappe.as_json([doc.assigned_to]),
        "description": _("Resident request assigned for follow-up: {0}").format(doc.name),
        "priority": doc.priority if doc.priority in ("Low", "Medium", "High") else "Medium",
    })
    doc.modified = frappe.db.get_value(doc.doctype, doc.name, "modified")

def _validate_status_transition(doc):
    status = doc.status or "New"

    if status == "Assigned" and not doc.assigned_to:
        doc.status = status = "New"

    if status in ("Resolved", "Closed") and not doc.resolution_notes:
        frappe.throw(_("Resolution Notes are required when closing or resolving a request."))

    if status == "Closed" and not doc.closed_on:
        doc.closed_on = frappe.utils.today()

    if status == "Closed" and not doc.closed_by:
        doc.closed_by = frappe.session.user

def _populate_location_from_token(doc):
    if not doc.location_token:
        return

    qr = frappe.get_all(
        "QR Location",
        filters={"location_token": doc.location_token, "is_active": 1},
        fields=["accommodation_site", "building", "room"],
        limit=1,
    )
    if not qr:
        return

    doc.accommodation_site = qr[0].accommodation_site
    doc.building = qr[0].building
    doc.room = qr[0].room

def _apply_priority_rules(doc):
    text = f"{doc.request_category or ''} {doc.description or ''}".lower()

    critical_terms = (
        "fire",
        "electrical hazard",
        "structural",
        "contamination",
        "no drinking water",
        "severe pest",
        "injury",
    )
    high_terms = (
        "bathroom leak",
        "broken bed",
        "missing locker",
        "security",
    )

    def _matches(term):
        return re.search(r"\b" + re.escape(term) + r"\b", text) is not None

    _AC_PATTERN = re.compile(r"\ba[/\-]?c\b|air.?condi", re.IGNORECASE)

    if any(_matches(term) for term in critical_terms):
        doc.priority = "Critical"
    elif (bool(_AC_PATTERN.search(text)) or any(_matches(term) for term in high_terms)) and doc.priority in (None, "", "Low", "Medium"):
        doc.priority = "High"

@frappe.whitelist(methods=["POST"])
def convert_request(source_name):
    frappe.has_permission("Resident Request", "write", doc=source_name, throw=True)

    source = frappe.get_doc("Resident Request", source_name)

    if source.target_doctype and source.target_document:
        if frappe.db.exists(source.target_doctype, source.target_document):
            return {
                "target_doctype": source.target_doctype,
                "target_document": source.target_document,
                "already_converted": True,
            }

    target_doctype = _CATEGORY_TARGET.get(source.request_category)
    if not target_doctype:
        frappe.throw(
            _("Requests in category {0} are resolved directly and have no target document to create.")
            .format(_(source.request_category or "Other"))
        )

    builders = {
        "Maintenance Request": _build_maintenance_request,
        "Safety Incident": _build_safety_incident,
        "Custody Issue": _build_custody_issue,
    }
    target = builders[target_doctype](source)
    target.insert(ignore_permissions=False)

    _link_target_to_request(source, target.doctype, target.name)

    return {
        "target_doctype": target.doctype,
        "target_document": target.name,
        "already_converted": False,
    }

def _link_target_to_request(source, target_doctype, target_name):
    updates = {"target_doctype": target_doctype, "target_document": target_name}
    if source.status in (None, "", "New", "Triaged", "Assigned"):
        updates["status"] = "In Progress"
    frappe.db.set_value("Resident Request", source.name, updates)

def _common_location(source, target):
    target.building = source.building
    target.room = source.room
    if source.bed:
        target.bed = source.bed

def _build_maintenance_request(source):
    target = frappe.new_doc("Maintenance Request")
    _common_location(source, target)
    target.issue_type = _CATEGORY_TO_ISSUE_TYPE.get(source.request_category, "Other")
    target.priority = source.priority or "Medium"
    target.issue_description = source.description or _("Converted from resident request {0}").format(source.name)
    target.reported_by = frappe.session.user
    target.status = "Open"
    return target

def _build_safety_incident(source):
    target = frappe.new_doc("Safety Incident")
    target.incident_datetime = frappe.utils.now_datetime()
    target.building = source.building
    target.specific_location = source.issue_location
    _severity_map = {"Critical": "Critical", "High": "High", "Medium": "Medium", "Low": "Low"}
    target.severity = _severity_map.get(source.priority, "Medium")
    target.description = source.description or _("Converted from resident request {0}").format(source.name)
    target.reported_by = frappe.session.user
    return target

def _build_custody_issue(source):
    target = frappe.new_doc("Custody Issue")
    target.issue_date = frappe.utils.today()
    target.building = source.building
    if source.party_type and source.party:
        target.party_type = source.party_type
        target.party = source.party
    target.remarks = source.description or _("Converted from resident request {0}").format(source.name)
    return target

_TRIAGE_NEXT = {
    "New": "Triaged",
    "Triaged": "In Progress",
    "In Progress": "Waiting Evidence",
    "Waiting Evidence": "In Progress",
}

@frappe.whitelist(methods=["POST"])
def advance_triage_status(name, to_status):
    frappe.has_permission("Resident Request", "write", doc=name, throw=True)

    doc = frappe.get_doc("Resident Request", name)
    if doc.status == to_status:
        return {"name": doc.name, "status": doc.status, "changed": False}

    expected = _TRIAGE_NEXT.get(doc.status or "New")
    if to_status != expected:
        frappe.throw(
            _("Cannot advance {0} from {1} to {2} here. Open the request to set the required fields.").format(
                doc.name, _(doc.status or "New"), _(to_status)
            )
        )

    doc.status = to_status
    doc.save()
    return {"name": doc.name, "status": doc.status, "changed": True}

BULK_TRIAGE_SYNC_LIMIT = 50

_BULK_TRIAGE_SAVEPOINT = "resident_request_bulk_triage_row"

@frappe.whitelist(methods=["POST"])
def bulk_triage(names):
    if isinstance(names, str):
        names = frappe.parse_json(names)
    names = names or []

    if len(names) > BULK_TRIAGE_SYNC_LIMIT:
        frappe.enqueue(
            "apex.habitat.doctype.resident_request.resident_request._bulk_triage_job",
            queue="short",
            job_id=bulk_triage_job_id(names),
            deduplicate=True,
            names=names,
        )
        return {"advanced": None, "total": len(names), "queued": True}

    return apply_bulk_triage(names)

def bulk_triage_job_id(names) -> str:
    return "bulk_triage:" + sha256_hash(
        "|".join(sorted(str(n) for n in names or []))
    )[:24]


def apply_bulk_triage(names):
    advanced = 0
    for name in names or []:
        frappe.db.savepoint(_BULK_TRIAGE_SAVEPOINT)
        try:
            frappe.has_permission("Resident Request", "write", doc=name, throw=True)
            doc = frappe.get_doc("Resident Request", name, for_update=True)
            if doc.status not in (None, "", "New"):
                continue
            doc.status = "Triaged"
            doc.save()
            advanced += 1
        except Exception:
            frappe.db.rollback(save_point=_BULK_TRIAGE_SAVEPOINT)
            frappe.log_error(
                message=frappe.get_traceback(),
                title=f"Bulk triage failed for {name}"[:140],
            )
    return {"advanced": advanced, "total": len(names or [])}

def _bulk_triage_job(names):
    apply_bulk_triage(names)
