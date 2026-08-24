# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate, now, today

from apex.habitat.doctype.housing_inventory.housing_inventory import reflect_completed_maintenance
from apex.habitat.maintenance_engine import post_maintenance_cost, reverse_maintenance_cost


class MaintenanceWorkOrder(Document):
    def on_cancel(self):
        self._reverse_accommodation_memo()

        reverse_maintenance_cost(self.name)

        if not self.maintenance_request:
            return
        if not frappe.db.exists("DocType", "Maintenance Request"):
            return
        request = frappe.get_doc(
            "Maintenance Request", self.maintenance_request, for_update=True
        )
        if (
            self.status in ("Planned", "In Progress")
            and request.docstatus == 1
            and request.status == "In Progress"
        ):
            request.db_set("status", "Open")

    def _reverse_accommodation_memo(self):
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
        }).insert(ignore_permissions=True)


def validate(doc, method=None):
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
                "status": ["in", ["Draft", "Planned", "In Progress"]],
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
    request = None
    if frappe.db.exists("DocType", "Maintenance Request") and doc.maintenance_request:
        request = frappe.get_doc(
            "Maintenance Request", doc.maintenance_request, for_update=True
        )
        if request.docstatus != 1 or request.status != "Open":
            frappe.throw(
                _(
                    "Only an open submitted Maintenance Request can be started by a Work Order."
                )
            )

    doc.db_set("status", "Planned")
    if request:
        request.db_set("status", "In Progress")


def before_cancel(doc, method=None):
    if not doc.cancellation_reason:
        frappe.throw(_("Cancellation Reason is required before cancelling a Maintenance Work Order."))


@frappe.whitelist(methods=["POST"])
def start_work(work_order):
    doc = frappe.get_doc("Maintenance Work Order", work_order, for_update=True)
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
    doc = frappe.get_doc("Maintenance Work Order", work_order, for_update=True)
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
    notes = str(completion_notes or doc.completion_notes or "").strip()
    if not start_date:
        frappe.throw(_("Actual Start Date is required to mark Completed."))
    if getdate(end_date) < getdate(start_date):
        frappe.throw(_("Actual End Date must be on or after Actual Start Date."))
    if not photo:
        frappe.throw(_("A completion photo is required before closing a Maintenance Work Order."))
    if not notes:
        frappe.throw(_("Completion Notes are required before closing a Maintenance Work Order."))

    request = None
    if frappe.db.exists("DocType", "Maintenance Request") and doc.maintenance_request:
        request = frappe.get_doc(
            "Maintenance Request", doc.maintenance_request, for_update=True
        )
        if request.docstatus != 1 or request.status != "In Progress":
            frappe.throw(
                _(
                    "Only an in-progress submitted Maintenance Request can be resolved by a Work Order."
                )
            )

    ledger_posted = False
    cost = flt(doc.total_procurement_cost)

    evidence = {
        "actual_start_date": start_date,
        "actual_end_date": end_date,
        "completion_photo": photo,
        "status": "Completed",
        "verified_by": frappe.session.user,
        "completed_on": now(),
        "completion_notes": notes,
    }
    doc.db_set(evidence)

    if request:
        request.db_set(
            {"status": "Resolved", "resolution_notes": notes},
        )

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
        }).insert(ignore_permissions=True)
        ledger_posted = True

    post_maintenance_cost(doc)

    doc.add_comment("Comment", _("Marked Completed via controlled method."))
    return {"status": "Completed", "ledger_posted": ledger_posted, "cost": cost}
