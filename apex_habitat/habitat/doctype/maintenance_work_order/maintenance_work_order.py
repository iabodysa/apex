"""Maintenance Work Order controller."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class MaintenanceWorkOrder(Document):
    def on_cancel(self):
        """Reverse the completion side-effects so a cancelled Work Order does not
        leave an orphan Accommodation Ledger memo or a Maintenance Request stuck
        Closed/In Progress.

        Native class method (Frappe fires it on cancel; no hooks.py doc_event is
        needed). Mirrors the Dispatch Trip / Fuel Request cancel-reversal pattern:
        net out the operational memo this Work Order posted (keyed by
        source_doctype/source_name) and release the linked request back to Open.
        Open is the request's pre-Work-Order state; a request a human has since
        moved to a terminal Resolved/Cancelled is left untouched."""
        for row in frappe.get_all(
            "Accommodation Ledger",
            filters={"source_doctype": "Maintenance Work Order", "source_name": self.name},
            pluck="name",
        ):
            frappe.delete_doc("Accommodation Ledger", row, ignore_permissions=True, force=True)  # audit-ok — reversing a system memo this Work Order posted

        if not self.maintenance_request:
            return
        if not frappe.db.exists("DocType", "Maintenance Request"):
            return
        mr_status = frappe.db.get_value("Maintenance Request", self.maintenance_request, "status")
        if mr_status in ("In Progress", "Closed"):
            frappe.db.set_value(
                "Maintenance Request", self.maintenance_request, "status", "Open"
            )


def validate(doc, method=None):
    if doc.planned_end_date and doc.planned_start_date:
        if doc.planned_end_date < doc.planned_start_date:
            frappe.throw(_("Planned End Date must be on or after Planned Start Date."))
    # [#j3wyod]
    if doc.maintenance_request:
        dup = frappe.db.exists(
            "Maintenance Work Order",
            {
                "maintenance_request": doc.maintenance_request,
                "docstatus": ["!=", 2],
                "name": ["!=", doc.name or ""],
            },
        )
        if dup:
            frappe.throw(
                _("A Work Order already exists for this Maintenance Request: {0}").format(dup)
            )
    # Procurement lines carry estimated_cost (Maintenance Procurement Item has no
    # "amount" field); summing a non-existent key left the total stuck at 0.
    doc.total_procurement_cost_sar = sum(
        flt(row.get("estimated_cost") or 0) for row in (doc.procurement_items or [])
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
    doc = frappe.get_doc("Maintenance Work Order", work_order)
    # [#eu1e7a]
    frappe.has_permission("Maintenance Work Order", "write", doc=doc, throw=True)

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

    doc = frappe.get_doc("Maintenance Work Order", work_order)
    frappe.has_permission("Maintenance Work Order", "write", doc=doc, throw=True)

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

        # db_set above fires no on_update doc_event, so reflect from this chokepoint.
        from apex_habitat.habitat.doctype.housing_inventory.housing_inventory import reflect_completed_maintenance
        reflect_completed_maintenance(doc)

        already_posted = frappe.db.exists(
            "Accommodation Ledger",
            {"source_doctype": "Maintenance Work Order", "source_name": doc.name},
        )
        if cost > 0 and not already_posted:
            # [#c07kbo]
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
            }).insert(ignore_permissions=True)  # audit-ok — system ledger memo on completion, gated by Work Order write (above)
            ledger_posted = True
    except Exception:
        frappe.db.rollback()
        frappe.throw(_("Could not complete the Work Order. No changes were saved. Please try again or contact support."))

    doc.add_comment("Comment", _("Marked Completed via controlled method."))
    return {"status": "Completed", "ledger_posted": ledger_posted, "cost": cost}
