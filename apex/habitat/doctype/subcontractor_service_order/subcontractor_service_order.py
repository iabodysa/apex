# Copyright (c) 2026, afmcoltd
"""Subcontractor Service Order controller.

Why Finance Manager holds a permlevel-1 row here and NO permlevel-0 row.
It is a deliberate field overlay, not an omission: the role may read and set
``service_cost`` on an order that Accommodation Manager opens, and may not open,
create, submit or cancel it. Document access is resolved from permlevel-0 rows only,
field access is resolved separately and unions every permlevel across the user's roles,
so the two are independent grants -- the row activates the moment one user holds both
roles, with no DocPerm edit. No shipped role profile bundles them today, so this
overlay is dormant until an administrator does. The framework's rule, written here rather
than pointed at: permlevel access is the UNION of the caller's roles
(frappe/permissions.py get_role_permissions), so a user holding both roles reads the
union of both field sets and no DocPerm edit is needed to widen him.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt, nowdate

from apex.apex_core.utils.vat import apply_vat


class SubcontractorServiceOrder(Document):
    pass


def before_save(doc, method=None):
    """Defaults the order's company and restates its cost with VAT."""
    if not doc.company:
        from apex.apex_core.doctype.habitat_settings.habitat_settings import get_default_company
        doc.company = get_default_company()

    _price_from_lines(doc)
    apply_vat(doc, doc.service_cost)
    _stamp_confirmation(doc)


def _price_from_lines(doc):
    """Amount each line, and let the lines set the service cost when there are any.

    An order with no lines is a flat call-off against the contract rate, and
    ``service_cost`` stays what Finance typed — that permlevel-1 grant is the field
    overlay this controller's own header describes, and deriving unconditionally
    would take it away. The moment a line exists the total is arithmetic, not an
    opinion, so the typed figure gives way to it.
    """
    rows = doc.get("service_items") or []
    if not rows:
        return
    total = 0.0
    for row in rows:
        row.amount = flt(flt(row.qty) * flt(row.rate), doc.precision("service_cost"))
        total += row.amount
    doc.service_cost = flt(total, doc.precision("service_cost"))


def _stamp_confirmation(doc):
    """Record who confirmed the visit and when, so the tick binds a person.

    The order is what the contractor invoices against, and a bare checkbox on it names
    nobody. Clearing the tick clears the pair, so a withdrawn confirmation never leaves
    a name printed under it.
    """
    if doc.supervisor_confirmed:
        if not doc.confirmed_by:
            doc.confirmed_by = frappe.session.user
            doc.confirmed_on = frappe.utils.now()
    else:
        doc.confirmed_by = None
        doc.confirmed_on = None


@frappe.whitelist(methods=["POST"])
def start_work(service_order):
    """Transition Subcontractor Service Order from Scheduled to In Progress."""
    doc = frappe.get_doc("Subcontractor Service Order", service_order, for_update=True)
    frappe.has_permission("Subcontractor Service Order", "write", doc=doc, throw=True)

    if doc.docstatus != 1:
        frappe.throw(_("Only submitted Service Orders can be started."))
    if doc.status != "Scheduled":
        frappe.throw(_("Only Service Orders with status Scheduled can be marked In Progress."))

    doc.db_set("status", "In Progress")
    doc.add_comment("Comment", _("Work started — status set to In Progress."))
    return {"status": "In Progress"}


@frappe.whitelist(methods=["POST"])
def mark_completed(
    service_order,
    supervisor_confirmed=None,
    completion_photo=None,
    visit_notes=None,
    actual_visit_date=None,
):
    """Transition Subcontractor Service Order from In Progress to Completed, and
    record the visit evidence in the same call.

    Controlled completion gate mirroring start_work / mark_missed: only a submitted
    order that is In Progress may be marked Completed, so the terminal state is
    reached through a guarded chokepoint rather than a free-form status edit.
    """
    doc = frappe.get_doc("Subcontractor Service Order", service_order, for_update=True)
    frappe.has_permission("Subcontractor Service Order", "write", doc=doc, throw=True)

    if doc.docstatus != 1:
        frappe.throw(_("Only submitted Service Orders can be marked Completed."))
    if doc.status != "In Progress":
        frappe.throw(_("Only Service Orders with status In Progress can be marked Completed."))

    evidence = {
        "supervisor_confirmed": cint(supervisor_confirmed) if supervisor_confirmed is not None else None,
        "completion_photo": completion_photo,
        "visit_notes": visit_notes,
        "actual_visit_date": actual_visit_date,
    }
    for fieldname, value in evidence.items():
        if value is not None:
            doc.db_set(fieldname, value)

    doc.db_set("status", "Completed")
    doc.add_comment("Comment", _("Marked Completed via controlled method."))
    return {"status": "Completed"}


@frappe.whitelist(methods=["POST"])
def mark_missed(service_order):
    """Transition Subcontractor Service Order from In Progress to Missed."""
    doc = frappe.get_doc("Subcontractor Service Order", service_order, for_update=True)
    frappe.has_permission("Subcontractor Service Order", "write", doc=doc, throw=True)

    if doc.docstatus != 1:
        frappe.throw(_("Only submitted Service Orders can be marked Missed."))
    if doc.status != "In Progress":
        frappe.throw(_("Only Service Orders with status In Progress can be marked Missed."))

    scheduled_date = getattr(doc, "scheduled_date", None)
    if scheduled_date and scheduled_date > nowdate():
        frappe.throw(_("Cannot mark Missed before the scheduled date ({0}).").format(scheduled_date))

    doc.db_set("status", "Missed")
    doc.add_comment("Comment", _("Marked Missed — work was not completed by the scheduled date."))
    return {"status": "Missed"}
