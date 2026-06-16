from __future__ import annotations

import re

import frappe
from frappe import _
from frappe.model.document import Document
from apex_habitat.apex_core.utils.party_link import sync_party_employee


class AccommodationResidentRequest(Document):
    pass


# [#dojvco]
# [#dvwgwi]
# [#6wuno8]
# [#oeibgt]
# [#8yax5d]
# [#929tdo]
# [#91azr6]
_CATEGORY_TARGET = {
    "Maintenance": "Maintenance Request",
    "Water": "Maintenance Request",
    "Electrical": "Maintenance Request",
    "AC": "Maintenance Request",
    "Plumbing": "Maintenance Request",
    "Cleaning": "Maintenance Request",
    "Pest Control": "Maintenance Request",
    "Facility Item": "Maintenance Request",
    "Safety": "Habitat Safety Incident",
    "Custody": "Custody Issue",
}

# [#oc09f7]
# [#h3xt26]
# [#3rx2wp]
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
    # [#t6k3lg]
    # [#191rhm]
    # [#csemjd]
    # [#ekmtvc]
    # [#jy7qnx]
    if not doc.anonymous_tracking_code:
        doc.anonymous_tracking_code = frappe.generate_hash(length=8).upper()

    if not doc.source_channel:
        doc.source_channel = "QR Web Form"

    if not doc.status:
        doc.status = "New"

    _populate_location_from_token(doc)
    _apply_priority_rules(doc)


def validate(doc, method=None):
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

    def _matches(term):
        # [#pwhqtz]
        # [#p1lmz6]
        # [#lmd8ij]
        return re.search(r"\b" + re.escape(term) + r"\b", text) is not None

    if any(_matches(term) for term in critical_terms):
        doc.priority = "Critical"
    elif any(_matches(term) for term in high_terms) and doc.priority in (None, "", "Low", "Medium"):
        doc.priority = "High"


# [#rudcur]
# [#6lr7y8]
# [#4fs9jj]
# [#hv1ioz]
# [#djcs9g]
# [#1v6swm]
# [#4ivwxk]
# [#ma2uhs]
# [#rudcur]


@frappe.whitelist(methods=["POST"])
def convert_request(source_name):
    """Create the category-appropriate operational document from a resident
    request, link it back via target_doctype / target_document, and advance the
    request to In Progress. Returns the new target's doctype + name so the
    client can route to it.

    Idempotent: if the request was already converted, the existing target is
    returned instead of creating a duplicate."""
    frappe.has_permission("Accommodation Resident Request", "write", doc=source_name, throw=True)

    source = frappe.get_doc("Accommodation Resident Request", source_name)

    # [#hau1ba]
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
        "Habitat Safety Incident": _build_safety_incident,
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
    # [#h9xuau]
    # [#q4p36b]
    if source.status in (None, "", "New", "Triaged", "Assigned"):
        updates["status"] = "In Progress"
    frappe.db.set_value("Accommodation Resident Request", source.name, updates)


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
    target = frappe.new_doc("Habitat Safety Incident")
    target.incident_datetime = frappe.utils.now_datetime()
    target.accommodation_building = source.building
    target.specific_location = source.issue_location
    # [#nstnl0]
    # [#s4oovn]
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
