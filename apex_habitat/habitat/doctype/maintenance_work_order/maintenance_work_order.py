"""Maintenance Work Order controller."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class MaintenanceWorkOrder(Document):
    def before_save(self):
        # Validate document properties
        if self.doctype != "Maintenance Work Order":
            frappe.throw("DocType mismatch")


def validate(doc, method=None):
    if doc.planned_end_date and doc.planned_start_date:
        if doc.planned_end_date < doc.planned_start_date:
            frappe.throw(_("Planned End Date must be on or after Planned Start Date."))
    doc.total_procurement_cost_sar = sum(
        flt(row.get("amount") or 0) for row in (doc.procurement_items or [])
    )


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


def on_update(doc, method=None):
    """Post a one-time operational maintenance cost row to the Accommodation
    Ledger when the work order is marked Completed.

    Operational Memo only — no GL impact. Idempotent: a second ledger row is
    never created for the same work order.
    """
    if doc.status != "Completed" or not doc.building:
        return
    cost = flt(doc.total_procurement_cost_sar)
    if cost <= 0:
        return
    if frappe.db.exists(
        "Accommodation Ledger",
        {"source_doctype": "Maintenance Work Order", "source_name": doc.name},
    ):
        return

    from frappe.utils import today

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
