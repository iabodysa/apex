# Copyright (c) 2026, AFMCO and contributors
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
Proof and the framework citations are in
``apex/habitat/doctype/custody_damage_assessment/test_finance_manager_field_overlay.py``.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class MaintenanceRequest(Document):
    pass


def before_save(doc, method=None):
    if doc.is_new() and not doc.reported_by:
        doc.reported_by = frappe.session.user

    if not doc.company:
        from apex.apex_core.doctype.habitat_settings.habitat_settings import (
            get_default_company,
        )
        doc.company = get_default_company()

    _validate_status_rules(doc)


def _validate_status_rules(doc):
    status = doc.status or "Open"
    if status == "Assigned" and not doc.assigned_to:
        frappe.throw(_("Assigned To is required when status is Assigned."))
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
