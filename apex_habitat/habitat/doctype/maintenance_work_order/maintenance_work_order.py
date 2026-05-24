"""Maintenance Work Order controller."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class MaintenanceWorkOrder(Document):
    pass


def validate(doc, method=None):
    if doc.planned_end_date and doc.planned_start_date:
        if doc.planned_end_date < doc.planned_start_date:
            frappe.throw(_("Planned End Date must be on or after Planned Start Date."))
    doc.total_procurement_cost_sar = sum(
        flt(row.get("amount") or 0) for row in (doc.procurement_items or [])
    )
    if doc.status in ("Completed", "Closed") and not doc.completion_photo:
        frappe.throw(_("A completion photo is required before closing a Maintenance Work Order."))


def on_submit(doc, method=None):
    doc.db_set("status", "Planned")
    if frappe.db.exists("DocType", "Maintenance Request") and doc.maintenance_request:
        mr = frappe.get_doc("Maintenance Request", doc.maintenance_request)
        if mr.docstatus == 1:
            mr_status_field = {f.fieldname for f in frappe.get_meta("Maintenance Request").fields}
            if "status" in mr_status_field:
                frappe.db.set_value("Maintenance Request", doc.maintenance_request, "status", "In Progress")


def before_cancel(doc, method=None):
    if not doc.cancellation_reason:
        frappe.throw(_("Cancellation Reason is required before cancelling a Maintenance Work Order."))


@frappe.whitelist(methods=["POST"])
def start_work(work_order):
    """Transition Maintenance Work Order from Planned to In Progress."""
    if not frappe.has_permission("Maintenance Work Order", "write"):
        frappe.throw(_("Not permitted"), frappe.PermissionError)
        
    doc = frappe.get_doc("Maintenance Work Order", work_order)

    if doc.docstatus != 1:
        frappe.throw(_("Only submitted Work Orders can be started."))
    if doc.status != "Planned":
        frappe.throw(_("Only Work Orders with status Planned can be marked In Progress."))

    doc.db_set("status", "In Progress")
    doc.add_comment("Comment", _("Work started — status set to In Progress."))
    return {"status": "In Progress"}


@frappe.whitelist(methods=["POST"])
def mark_completed(work_order, completion_notes=None):
    """Controlled transition to Completed.

    The status field is not changed through a normal after-submit save. This
    method performs the transition and posts a one-time operational memo row.
    No GL Entry, Payment Entry, Purchase Invoice, or salary document is created.
    """
    from frappe.utils import today

    if not frappe.has_permission("Maintenance Work Order", "write"):
        frappe.throw(_("Not permitted"), frappe.PermissionError)

    doc = frappe.get_doc("Maintenance Work Order", work_order)

    if doc.docstatus != 1:
        frappe.throw(_("Only submitted Maintenance Work Orders can be marked Completed."))
    if doc.status == "Completed":
        frappe.throw(_("This Maintenance Work Order is already Completed."))
    if not doc.building:
        frappe.throw(_("Building is required to mark Completed."))
    if not doc.actual_start_date or not doc.actual_end_date:
        frappe.throw(_("Actual Start Date and Actual End Date are required to mark Completed."))
    if not doc.completion_photo:
        frappe.throw(_("A completion photo is required before closing a Maintenance Work Order."))

    ledger_posted = False
    cost = flt(doc.total_procurement_cost_sar)

    try:
        doc.db_set("status", "Completed")
        if completion_notes and not doc.completion_notes:
            doc.db_set("completion_notes", completion_notes)

        if frappe.db.exists("DocType", "Maintenance Request") and doc.maintenance_request:
            mr_status_field = {f.fieldname for f in frappe.get_meta("Maintenance Request").fields}
            if "status" in mr_status_field:
                frappe.db.set_value("Maintenance Request", doc.maintenance_request, "status", "Closed")

        already_posted = frappe.db.exists(
            "Accommodation Ledger",
            {"source_doctype": "Maintenance Work Order", "source_name": doc.name},
        )
        if cost > 0 and not already_posted:
            # Permission bypass intentional: Accommodation Ledger is an internal system/audit
            # write that must succeed regardless of the calling user's ledger permissions.
            frappe.get_doc({
                "doctype": "Accommodation Ledger",
                "posting_date": doc.actual_end_date or today(),
                "building": doc.building,
                "ledger_type": "Maintenance",
                "total_site_cost": cost,
                "capacity_denominator": 0,
                "employee_daily_share": 0,
                "posting_mode": "Operational Memo",
                "source_doctype": "Maintenance Work Order",
                "source_name": doc.name,
                "allocation_basis": "Direct",
                "allocation_period_start": doc.actual_start_date,
                "allocation_period_end": doc.actual_end_date,
            }).insert(ignore_permissions=True)
            ledger_posted = True
    except Exception:
        frappe.db.rollback()
        frappe.throw(_("Could not complete the Work Order. No changes were saved. Please try again or contact support."))

    doc.add_comment("Comment", _("Marked Completed via controlled method."))
    return {"status": "Completed", "ledger_posted": ledger_posted, "cost": cost}
