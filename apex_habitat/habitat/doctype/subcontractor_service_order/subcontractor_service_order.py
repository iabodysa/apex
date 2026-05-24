"""Subcontractor Service Order controller."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import nowdate


class SubcontractorServiceOrder(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        actual_visit_date: DF.Date | None
        amended_from: DF.Link | None
        building: DF.Link
        company: DF.Link | None
        completion_photo: DF.AttachImage | None
        contract: DF.Link
        cost_center: DF.Link | None
        linked_purchase_invoice: DF.Link | None
        naming_series: DF.Literal["SSO-.YYYY.-.#####"]
        scheduled_date: DF.Date
        service_cost_sar: DF.Currency
        service_type: DF.Data | None
        status: DF.Literal["Scheduled", "In Progress", "Completed", "Missed", "Cancelled"]
        supervisor_confirmed: DF.Check
        supplier: DF.Link | None
        visit_notes: DF.SmallText | None
    # end: auto-generated types
    pass


def before_save(doc, method=None):
    if not doc.company:
        from apex_habitat.habitat.doctype.habitat_settings.habitat_settings import get_default_company
        doc.company = get_default_company()


@frappe.whitelist(methods=["POST"])
def start_work(service_order):
    """Transition Subcontractor Service Order from Scheduled to In Progress."""
    if not frappe.has_permission("Subcontractor Service Order", "write"):
        frappe.throw(_("Not permitted"), frappe.PermissionError)

    doc = frappe.get_doc("Subcontractor Service Order", service_order)

    if doc.docstatus != 1:
        frappe.throw(_("Only submitted Service Orders can be started."))
    if doc.status != "Scheduled":
        frappe.throw(_("Only Service Orders with status Scheduled can be marked In Progress."))

    doc.db_set("status", "In Progress")
    doc.add_comment("Comment", _("Work started — status set to In Progress."))
    return {"status": "In Progress"}


@frappe.whitelist(methods=["POST"])
def mark_missed(service_order):
    """Transition Subcontractor Service Order from In Progress to Missed."""
    if not frappe.has_permission("Subcontractor Service Order", "write"):
        frappe.throw(_("Not permitted"), frappe.PermissionError)

    doc = frappe.get_doc("Subcontractor Service Order", service_order)

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
