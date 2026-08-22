# Copyright (c) 2026, afmcoltd
"""Maintenance Request controller.

Why Finance Manager holds a permlevel-1 row here and NO permlevel-0 row, and
why this DocType is the exception among the five that share the shape. It is a
deliberate field overlay: the role may read and set ``cost_of_repair`` and
``cost_center`` on a request another role opens. Document access is resolved from
permlevel-0 rows only, field access is resolved separately and unions every permlevel
across the user's roles, so the two are independent grants.

The exception: this DocType also ships an ``All`` permlevel-0 row (read+create,
if_owner), and every logged-in user holds ``All``. ``if_owner`` never restricts
``create``, so a Finance-Manager-only user can raise their OWN request and the
permlevel-1 row keeps the cost they enter instead of resetting it. They still cannot
edit or submit it. Elsewhere in the five the overlay needs a second role; here it is
already live, so do not reason about this DocType from the other four.
The framework's rule, written here rather than pointed at: permlevel access is the UNION
of the caller's roles (frappe/permissions.py get_role_permissions), so a user holding both
roles reads the union of both field sets and no DocPerm edit is needed to widen him.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.desk.form.assign_to import close_all_assignments
from frappe.model.document import Document
from frappe.utils import flt

_TRANSITION_SAVEPOINT = "maintenance_request_transition"


class MaintenanceRequest(Document):
    pass


def validate(doc, method=None):
    """Default request ownership and enforce lifecycle rules on save and submit."""
    _guard_status(doc)
    if doc.is_new() and not doc.reported_by:
        doc.reported_by = frappe.session.user

    if not doc.company:
        from apex.apex_core.doctype.habitat_settings.habitat_settings import (
            get_default_company,
        )
        doc.company = get_default_company()

    _validate_status_rules(doc)


def _guard_status(doc):
    """Keep lifecycle status under server-owned work-order and action transitions."""
    if doc.is_new():
        doc.status = "Open"
        return
    if doc.has_value_changed("status"):
        frappe.throw(
            _("Use the Maintenance Request actions to change Status."),
            frappe.PermissionError,
        )


def _validate_status_rules(doc):
    """Blocks a resolved request with no notes or a negative repair cost."""
    status = doc.status or "Open"
    if status in ("Resolved", "Closed") and not doc.resolution_notes:
        frappe.throw(_("Resolution Notes are required to resolve or close a Maintenance Request."))
    if flt(doc.cost_of_repair) < 0:
        frappe.throw(_("Cost of Repair cannot be negative."))


@frappe.whitelist(methods=["POST"])
def make_work_order(source_name, target_doc=None):
    """Create a Maintenance Work Order from this request.

    field_map is intentionally omitted for building/issue_type: get_mapped_doc
    copies same-named fields automatically (mapper lines 190-195).  status is
    excluded via field_no_map so the source "Open" value is never copied; the
    correct "Planned" value is written by set_missing_values instead.

    Fields on Maintenance Request that have NO matching fieldname on Maintenance
    Work Order (room, bed, priority) are therefore never referenced here, which
    prevents the silent-drop data-loss described above.
    """
    frappe.has_permission("Maintenance Request", "read", doc=source_name, throw=True)
    from frappe.model.mapper import get_mapped_doc

    def set_missing_values(source, target):
        """Sets the mapped Work Order's source request link and status to Planned."""
        target.maintenance_request = source.name
        target.status = "Planned"

    doclist = get_mapped_doc(
        "Maintenance Request",
        source_name,
        {
            "Maintenance Request": {
                "doctype": "Maintenance Work Order",
                "field_no_map": ["status"],
            }
        },
        target_doc,
        set_missing_values,
    )

    return doclist


def _locked_request(name: str):
    """Load one request under a row lock and enforce native write permission."""
    doc = frappe.get_doc("Maintenance Request", name, for_update=True)
    doc.check_permission("write")
    return doc


@frappe.whitelist(methods=["POST"])
def close_request(name: str) -> dict:
    """Close a resolved request and its native Frappe assignments atomically."""
    doc = _locked_request(name)
    if doc.docstatus != 1:
        frappe.throw(_("Only submitted Maintenance Requests can be closed."))
    if doc.status != "Resolved":
        frappe.throw(_("Only a resolved Maintenance Request can be closed."))

    frappe.db.savepoint(_TRANSITION_SAVEPOINT)
    try:
        doc.db_set("status", "Closed")
        close_all_assignments("Maintenance Request", doc.name)
        doc.add_comment("Comment", _("Maintenance Request closed."))
    except Exception:
        frappe.db.rollback(save_point=_TRANSITION_SAVEPOINT)
        raise
    return {"name": doc.name, "status": "Closed"}


@frappe.whitelist(methods=["POST"])
def reopen_request(name: str, reason: str) -> dict:
    """Return a resolved or closed request to Open with an auditable reason."""
    reason = str(reason or "").strip()
    if not reason:
        frappe.throw(_("A reason is required to reopen a Maintenance Request."))

    doc = _locked_request(name)
    if doc.docstatus != 1:
        frappe.throw(_("Only submitted Maintenance Requests can be reopened."))
    if doc.status not in ("Resolved", "Closed"):
        frappe.throw(_("Only a resolved or closed Maintenance Request can be reopened."))

    frappe.db.savepoint(_TRANSITION_SAVEPOINT)
    try:
        doc.db_set("status", "Open")
        doc.add_comment(
            "Comment",
            _("Maintenance Request reopened: {0}").format(reason),
        )
    except Exception:
        frappe.db.rollback(save_point=_TRANSITION_SAVEPOINT)
        raise
    return {"name": doc.name, "status": "Open"}
