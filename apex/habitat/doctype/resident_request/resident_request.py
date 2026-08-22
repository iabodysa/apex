# Copyright (c) 2026, afmcoltd
"""Resident Request controller."""

from __future__ import annotations

import re

import frappe
from frappe import _
from frappe.desk.form.assign_to import add as add_assignment
from frappe.desk.form.assign_to import close_all_assignments
from frappe.model.document import Document
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
    """Generates a tracking code, defaults channel and status, resolves location, sets priority."""
    if not doc.anonymous_tracking_code:
        doc.anonymous_tracking_code = frappe.generate_hash(length=8).upper()

    if not doc.source_channel:
        doc.source_channel = "QR Web Form"

    if not doc.status:
        doc.status = "New"

    _populate_location_from_token(doc)
    _apply_priority_rules(doc)

def validate(doc, method=None):
    """Resolves the location token, syncs the employee, blocks a bad token, and checks status rules.

    The honeypot is read HERE, not only in submit_resident_request: the live public form
    saves through Frappe's own ``web_form.accept``, which copies every web form field onto
    the document (frappe/website/doctype/web_form/web_form.py:632-647) and never touches
    the hardened endpoint beside it. Checked only there, the trap caught nothing."""
    if doc.get("website_field"):
        frappe.throw(_("Invalid submission."), frappe.PermissionError)

    _populate_location_from_token(doc)
    sync_party_employee(doc)
    if doc.location_token and not doc.building:
        frappe.throw(_("Invalid or inactive location token."))

    _validate_status_transition(doc)

def on_update(doc, method=None):
    """Native ToDo follow-up: when a request is Assigned to a user, put it in that
    user's desk queue; when it ends (Resolved/Rejected/Closed), close the open
    ToDos. Idempotent — never creates a duplicate ToDo for the same assignee."""
    _sync_assignment_todo(doc)

def _sync_assignment_todo(doc):
    """Drive Frappe's own assignment API rather than the records behind it.

    ``_assign`` is a cache the ToDo controller owns: ``ToDo.on_update`` ->
    ``update_in_reference`` (frappe/desk/doctype/todo/todo.py:87-120) rebuilds it from
    EVERY live ToDo on the document. Writing it here replaced that aggregate with the
    one name this field happens to hold, so a second assignee vanished from the desk
    badge. ``assign_to.set_status`` (frappe/desk/form/assign_to.py:228-230) likewise
    owns ``assigned_to`` and clears it when the assignment closes.

    ``add`` is already duplicate-safe: an assignee who holds an open ToDo on this
    document is skipped with a message, not re-assigned.

    The timestamp is re-read because the API writes ``assigned_to`` back on any DocType
    that owns a field of that name (frappe/desk/form/assign_to.py:97, and :228-230 on the
    closing side) with no ``update_modified=False``. The row's ``modified`` therefore
    moves while the caller still holds the pre-assignment value, and its next save of the
    same handle throws TimestampMismatchError."""
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
    """Enforce role-based state transition rules without a full Frappe Workflow."""
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
    """Sets the accommodation site, building and room from the active QR Location matching the token."""
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
    """Sets priority to Critical for hazard keywords, or to High for AC and other urgent keywords."""
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
        """Returns whether a term appears as a whole word in the combined category and description text."""
        return re.search(r"\b" + re.escape(term) + r"\b", text) is not None

    _AC_PATTERN = re.compile(r"\ba[/\-]?c\b|air.?condi", re.IGNORECASE)

    def _is_ac_request():
        """Returns whether the combined category and description text matches an air-conditioning pattern."""
        return bool(_AC_PATTERN.search(text))

    if any(_matches(term) for term in critical_terms):
        doc.priority = "Critical"
    elif (_is_ac_request() or any(_matches(term) for term in high_terms)) and doc.priority in (None, "", "Low", "Medium"):
        doc.priority = "High"

@frappe.whitelist(methods=["POST"])
def convert_request(source_name):
    """Create the category-appropriate operational document from a resident
    request, link it back via target_doctype / target_document, and advance the
    request to In Progress. Returns the new target's doctype + name so the
    client can route to it.

    Idempotent: if the request was already converted, the existing target is
    returned instead of creating a duplicate."""
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
    """Stamp the read-only traceability fields and advance status. Uses
    db.set_value (not a full save) so the read_only target_* fields are written
    server-side without re-running the request's own validate/on_update mid-flow,
    and without a timestamp-mismatch race."""
    updates = {"target_doctype": target_doctype, "target_document": target_name}
    if source.status in (None, "", "New", "Triaged", "Assigned"):
        updates["status"] = "In Progress"
    frappe.db.set_value("Resident Request", source.name, updates)

def _common_location(source, target):
    """Copies the building, room and bed from the source request onto the new target document."""
    target.building = source.building
    target.room = source.room
    if source.bed:
        target.bed = source.bed

def _build_maintenance_request(source):
    """Builds an unsaved Maintenance Request from the request's location, category and description."""
    target = frappe.new_doc("Maintenance Request")
    _common_location(source, target)
    target.issue_type = _CATEGORY_TO_ISSUE_TYPE.get(source.request_category, "Other")
    target.priority = source.priority or "Medium"
    target.issue_description = source.description or _("Converted from resident request {0}").format(source.name)
    target.reported_by = frappe.session.user
    target.status = "Open"
    return target

def _build_safety_incident(source):
    """Builds an unsaved Safety Incident from the request's location, severity and description."""
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
    """Builds an unsaved Custody Issue from the resident request's building, party and description."""
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
    """Advance one resident request to the next no-extra-data triage state from a
    phone-friendly list view. Reuses the controller save path so the canonical
    _validate_status_transition rule runs; rejects any jump that is not in the
    guard-free progression. Idempotent: a request already at to_status is a no-op."""
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

@frappe.whitelist(methods=["POST"])
def bulk_triage(names):
    """Bulk-advance a selection of New requests to Triaged (the universal first
    triage step). Skips any row not in New so a mixed selection partially applies
    rather than failing whole.

    Small selections run inline and return the count actually advanced (the desk
    list action shows it immediately). A selection larger than
    ``BULK_TRIAGE_SYNC_LIMIT`` is handed to a background job so the request returns
    at once instead of blocking the worker thread on an unbounded loop; the
    response then carries ``queued=True`` and ``advanced=None`` (the job applies
    the same per-row triage under the enqueuing user's permissions)."""
    if isinstance(names, str):
        names = frappe.parse_json(names)
    names = names or []

    if len(names) > BULK_TRIAGE_SYNC_LIMIT:
        frappe.enqueue(
            "apex.habitat.doctype.resident_request.resident_request._bulk_triage_job",
            queue="short",
            names=names,
        )
        return {"advanced": None, "total": len(names), "queued": True}

    return _apply_bulk_triage(names)

def _apply_bulk_triage(names):
    """Advance each New Resident Request in ``names`` to Triaged (per-row write
    permission checked); returns the count advanced. Shared body of the inline and
    the background bulk-triage paths."""
    advanced = 0
    for name in names or []:
        frappe.has_permission("Resident Request", "write", doc=name, throw=True)
        doc = frappe.get_doc("Resident Request", name)
        if doc.status not in (None, "", "New"):
            continue
        doc.status = "Triaged"
        doc.save()
        advanced += 1
    return {"advanced": advanced, "total": len(names or [])}

def _bulk_triage_job(names):
    """Background runner for a large bulk_triage selection (queued by ``bulk_triage``).
    Runs under the enqueuing user — frappe.enqueue captures the session user and
    the worker re-applies it via frappe.set_user — so the per-row write-permission
    check inside ``_apply_bulk_triage`` still applies."""
    _apply_bulk_triage(names)
