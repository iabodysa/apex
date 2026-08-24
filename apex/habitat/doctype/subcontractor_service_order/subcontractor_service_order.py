# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt, getdate, nowdate

from apex.apex_core.utils.company import resolve_company
from apex.apex_core.utils.vat import apply_vat


class SubcontractorServiceOrder(Document):
    pass


def before_save(doc, method=None):
    if not doc.company:
        doc.company = resolve_company("Habitat")

    _price_from_lines(doc)
    apply_vat(doc, doc.service_cost)
    _stamp_confirmation(doc)


def _price_from_lines(doc):
    rows = doc.get("service_items") or []
    if not rows:
        return
    total = 0.0
    for row in rows:
        row.amount = flt(flt(row.qty) * flt(row.rate), doc.precision("service_cost"))
        total += row.amount
    doc.service_cost = flt(total, doc.precision("service_cost"))


def _stamp_confirmation(doc):
    if doc.supervisor_confirmed:
        if not doc.confirmed_by:
            doc.confirmed_by = frappe.session.user
            doc.confirmed_on = frappe.utils.now()
    else:
        doc.confirmed_by = None
        doc.confirmed_on = None


@frappe.whitelist(methods=["POST"])
def start_work(service_order):
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
    doc = frappe.get_doc("Subcontractor Service Order", service_order, for_update=True)
    frappe.has_permission("Subcontractor Service Order", "write", doc=doc, throw=True)

    if doc.docstatus != 1:
        frappe.throw(_("Only submitted Service Orders can be marked Missed."))
    if doc.status != "In Progress":
        frappe.throw(_("Only Service Orders with status In Progress can be marked Missed."))

    scheduled_date = getattr(doc, "scheduled_date", None)
    if scheduled_date and getdate(scheduled_date) > getdate(nowdate()):
        frappe.throw(_("Cannot mark Missed before the scheduled date ({0}).").format(scheduled_date))

    doc.db_set("status", "Missed")
    doc.add_comment("Comment", _("Marked Missed — work was not completed by the scheduled date."))
    return {"status": "Missed"}
