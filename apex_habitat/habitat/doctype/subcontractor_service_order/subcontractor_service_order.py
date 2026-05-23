"""Subcontractor Service Order controller."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import nowdate


class SubcontractorServiceOrder(Document):
    def before_save(self):
        if not self.company:
            from apex_habitat.habitat.doctype.habitat_settings.habitat_settings import get_default_company
            self.company = get_default_company()


@frappe.whitelist()
def start_work(service_order):
    """Transition Subcontractor Service Order from Scheduled to In Progress."""
    doc = frappe.get_doc("Subcontractor Service Order", service_order)

    if doc.docstatus != 1:
        frappe.throw(_("Only submitted Service Orders can be started."))
    if doc.status != "Scheduled":
        frappe.throw(_("Only Service Orders with status Scheduled can be marked In Progress."))

    doc.db_set("status", "In Progress")
    doc.add_comment("Comment", _("Work started — status set to In Progress."))
    return {"status": "In Progress"}


@frappe.whitelist()
def mark_missed(service_order):
    """Transition Subcontractor Service Order from In Progress to Missed."""
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
