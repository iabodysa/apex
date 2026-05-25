from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


class AccommodationResidentRequest(Document):
    pass


def before_insert(doc, method=None):
    if doc.get("website_field"):
        frappe.throw("Invalid submission.", frappe.PermissionError)

    if not doc.anonymous_tracking_code:
        doc.anonymous_tracking_code = frappe.generate_hash(length=8).upper()

    if not doc.source_channel:
        doc.source_channel = "QR Web Form"

    if not doc.status:
        doc.status = "New"

    _populate_location_from_token(doc)
    _apply_priority_rules(doc)


def validate(doc, method=None):
    if doc.location_token and not doc.building:
        frappe.throw(_("Invalid or inactive location token."))

    _validate_status_transition(doc)


def on_update(doc, method=None):
    """Native ToDo follow-up: when a request is Assigned to a user, put it in that
    user's desk queue; when it ends (Resolved/Rejected/Closed), close the open
    ToDos. Idempotent — never creates a duplicate ToDo for the same assignee."""
    _sync_assignment_todo(doc)


def _sync_assignment_todo(doc):
    """Create/close the follow-up ToDo directly (not via assign_to.add, which would
    re-save this same document mid-on_update and raise a timestamp mismatch). The
    parent's `_assign` is updated with update_modified=False so the desk badge still
    shows without bumping this document's modified timestamp."""
    if doc.status in ("Resolved", "Rejected", "Closed"):
        open_todos = frappe.get_all(
            "ToDo",
            filters={"reference_type": doc.doctype, "reference_name": doc.name, "status": "Open"},
            pluck="name",
        )
        for todo in open_todos:
            frappe.db.set_value("ToDo", todo, "status", "Cancelled")
        if open_todos:
            frappe.db.set_value(doc.doctype, doc.name, "_assign", None, update_modified=False)
        return

    if doc.status != "Assigned" or not doc.assigned_to:
        return

    already = frappe.get_all(
        "ToDo",
        filters={"reference_type": doc.doctype, "reference_name": doc.name,
                 "allocated_to": doc.assigned_to, "status": "Open"},
        limit=1,
    )
    if already:
        return
    priority = doc.priority if doc.priority in ("Low", "Medium", "High") else "Medium"
    frappe.get_doc({
        "doctype": "ToDo",
        "allocated_to": doc.assigned_to,
        "reference_type": doc.doctype,
        "reference_name": doc.name,
        "description": _("Resident request assigned for follow-up: {0}").format(doc.name),
        "priority": priority,
        "assigned_by": frappe.session.user,
    }).insert(ignore_permissions=True)  # audit-ok
    frappe.db.set_value(doc.doctype, doc.name, "_assign",
                        frappe.as_json([doc.assigned_to]), update_modified=False)


def _validate_status_transition(doc):
    """Enforce role-based state transition rules without a full Frappe Workflow."""
    status = doc.status or "New"

    if status == "Assigned" and not doc.assigned_to:
        frappe.throw(_("Assigned To is required when status is Assigned."))

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
        "Accommodation QR Location",
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
        "ac",
        "air conditioning",
        "bathroom leak",
        "broken bed",
        "missing locker",
        "security",
    )

    if any(term in text for term in critical_terms):
        doc.priority = "Critical"
    elif any(term in text for term in high_terms) and doc.priority in (None, "", "Low", "Medium"):
        doc.priority = "High"
