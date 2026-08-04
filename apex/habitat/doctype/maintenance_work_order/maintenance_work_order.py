# Copyright (c) 2026, AFMCO and contributors
"""Maintenance Work Order controller."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate, today


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
        self._reverse_accommodation_memo()

        from apex.habitat.maintenance_engine import reverse_maintenance_cost
        reverse_maintenance_cost(self.name)

        if not self.maintenance_request:
            return
        if not frappe.db.exists("DocType", "Maintenance Request"):
            return
        mr_status = frappe.db.get_value("Maintenance Request", self.maintenance_request, "status")
        if mr_status in ("In Progress", "Closed"):
            frappe.db.set_value(
                "Maintenance Request", self.maintenance_request, "status", "Open"
            )

    def _reverse_accommodation_memo(self):
        """Post a negative mirror for the live completion memo this Work Order
        posted. Idempotent: skips if the original was already reversed."""
        original = frappe.db.get_value(
            "Accommodation Ledger",
            {
                "source_doctype": "Maintenance Work Order",
                "source_name": self.name,
                "reversal_of": ["is", "not set"],
            },
            ["name", "building", "ledger_type", "total_site_cost", "capacity_denominator"],
            as_dict=True,
        )
        if not original:
            return
        if frappe.db.exists("Accommodation Ledger", {"reversal_of": original.name}):
            return
        frappe.get_doc({
            "doctype": "Accommodation Ledger",
            "posting_date": today(),
            "building": original.building,
            "ledger_type": original.ledger_type,
            "total_site_cost": -flt(original.total_site_cost),
            "capacity_denominator": original.capacity_denominator or 0,
            "employee_daily_share": 0,
            "posting_mode": "Operational Memo",
            "source_doctype": "Maintenance Work Order",
            "source_name": self.name,
            "allocation_basis": "Direct",
            "reversal_of": original.name,
        }).insert(ignore_permissions=True)  # audit-ok — system ledger reversal this Work Order posted


def validate(doc, method=None):
    """Draft-time field checks, including the draft half of the actual-date ordering rule.

    ``validate`` cannot cover the after-submit half: ``run_before_save_methods``
    dispatches ``before_update_after_submit`` there, never ``validate``
    (frappe/model/document.py), so ``mark_completed`` re-checks the ordering itself.
    """
    if doc.planned_end_date and doc.planned_start_date:
        if doc.planned_end_date < doc.planned_start_date:
            frappe.throw(_("Planned End Date must be on or after Planned Start Date."))
    if doc.actual_end_date and doc.actual_start_date:
        if getdate(doc.actual_end_date) < getdate(doc.actual_start_date):
            frappe.throw(_("Actual End Date must be on or after Actual Start Date."))
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
    doc.total_procurement_cost = sum(
        flt(row.get("estimated_cost") or 0) for row in (doc.procurement_items or [])
    )
    if doc.status == "Completed" and not doc.completion_photo:
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
    """Transition Maintenance Work Order from Planned to In Progress, stamping the
    actual start date.

    Starting the job IS its actual start, so the date is recorded here rather than
    asked for. That matters because ``actual_start_date`` is deliberately not an
    allow_on_submit field — see ``mark_completed`` for why — which leaves this method
    and ``mark_completed`` its only writers once the Work Order is submitted.
    """
    doc = frappe.get_doc("Maintenance Work Order", work_order)
    frappe.has_permission("Maintenance Work Order", "write", doc=doc, throw=True)

    if doc.docstatus != 1:
        frappe.throw(_("Only submitted Work Orders can be started."))
    if doc.status != "Planned":
        frappe.throw(_("Only Work Orders with status Planned can be marked In Progress."))

    updates = {"status": "In Progress"}
    if not doc.actual_start_date:
        updates["actual_start_date"] = today()
    doc.db_set(updates)
    doc.add_comment("Comment", _("Work started — status set to In Progress."))
    return {"status": "In Progress", "actual_start_date": doc.actual_start_date}


@frappe.whitelist(methods=["POST"])
def mark_completed(
    work_order,
    completion_notes=None,
    actual_end_date=None,
    completion_photo=None,
    actual_start_date=None,
):
    """Record the technician's completion evidence and transition to Completed.

    Why the evidence travels through this method instead of the form. Saving a
    submitted document is ``update_after_submit``, and Frappe gates that on the
    SUBMIT permission, not write (``frappe/model/document.py`` set_docstatus). The
    Maintenance Technician holds write WITHOUT submit by design, so no field on a
    submitted Work Order is reachable from the form for the person doing the work —
    not even ``completion_photo``, whose Desk attach control issues
    ``frm.save("Update")`` once docstatus is 1. Widening the DocPerm to reach those
    fields would also hand the executing technician authority to submit and cancel
    the very Work Order they are working, which is the separation this DocType keeps.
    A Frappe Workflow transition is no better: it moves a state field and carries no
    payload, so it cannot capture two dates and a photo, and it still routes through
    save.

    So the date fields stay non-allow_on_submit and this method is their only writer
    at docstatus 1. It re-checks write itself because ``db_set`` goes straight to the
    database, skipping both the permission check and validate(), and it enforces the
    actual-date ordering here because validate() does not run on the after-submit path.

    The transition posts a one-time operational memo row. No GL Entry, Payment Entry,
    Purchase Invoice, or salary document is created.
    """
    doc = frappe.get_doc("Maintenance Work Order", work_order)
    frappe.has_permission("Maintenance Work Order", "write", doc=doc, throw=True)

    if doc.docstatus != 1:
        frappe.throw(_("Only submitted Maintenance Work Orders can be marked Completed."))
    if doc.status == "Completed":
        frappe.throw(_("This Maintenance Work Order is already Completed."))
    if doc.status != "In Progress":
        frappe.throw(
            _("Start the work first — only a Work Order In Progress can be Completed.")
        )
    if not doc.building:
        frappe.throw(_("Building is required to mark Completed."))

    start_date = actual_start_date or doc.actual_start_date
    end_date = actual_end_date or doc.actual_end_date or today()
    photo = completion_photo or doc.completion_photo
    if not start_date:
        frappe.throw(_("Actual Start Date is required to mark Completed."))
    if getdate(end_date) < getdate(start_date):
        frappe.throw(_("Actual End Date must be on or after Actual Start Date."))
    if not photo:
        frappe.throw(_("A completion photo is required before closing a Maintenance Work Order."))

    ledger_posted = False
    cost = flt(doc.total_procurement_cost)

    evidence = {
        "actual_start_date": start_date,
        "actual_end_date": end_date,
        "completion_photo": photo,
        "status": "Completed",
    }
    if completion_notes:
        evidence["completion_notes"] = completion_notes
    doc.db_set(evidence)

    if frappe.db.exists("DocType", "Maintenance Request") and doc.maintenance_request:
        mr_status_field = {f.fieldname for f in frappe.get_meta("Maintenance Request").fields}
        if "status" in mr_status_field:
            frappe.db.set_value("Maintenance Request", doc.maintenance_request, "status", "Closed")

    from apex.habitat.doctype.housing_inventory.housing_inventory import reflect_completed_maintenance
    reflect_completed_maintenance(doc)

    already_posted = frappe.db.exists(
        "Accommodation Ledger",
        {"source_doctype": "Maintenance Work Order", "source_name": doc.name},
    )
    if cost > 0 and not already_posted:
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

    from apex.habitat.maintenance_engine import post_maintenance_cost
    post_maintenance_cost(doc)

    doc.add_comment("Comment", _("Marked Completed via controlled method."))
    return {"status": "Completed", "ledger_posted": ledger_posted, "cost": cost}
