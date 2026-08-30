# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


UNIQUE_KEY = ["assignment", "task_catalog", "due_date", "docstatus"]
UNIQUE_KEY_NAME = "unique_sti_assignment_catalog_due_status"


class ScheduledTaskInstance(Document):
    pass


def on_doctype_update():
    frappe.db.add_unique(
        "Scheduled Task Instance",
        UNIQUE_KEY,
        constraint_name=UNIQUE_KEY_NAME,
    )


def on_submit(doc, method=None):
    if doc.status not in ("In Progress", "Completed", "Cancelled", "Overdue"):
        doc.db_set("status", "Open")


def before_cancel(doc, method=None):
    if not doc.cancellation_reason:
        frappe.throw(_("Cancellation Reason is required before cancelling a Scheduled Task Instance."))


@frappe.whitelist(methods=["POST"])
def start_task(task_instance):
    doc = frappe.get_doc("Scheduled Task Instance", task_instance, for_update=True)
    frappe.has_permission("Scheduled Task Instance", "write", doc=doc, throw=True)

    if doc.docstatus != 1:
        frappe.throw(_("Only submitted Task Instances can be started."))
    if doc.status != "Open":
        frappe.throw(_("Only Task Instances with status Open can be marked In Progress."))

    doc.db_set("status", "In Progress")
    doc.add_comment("Comment", _("Task started — status set to In Progress."))
    return {"status": "In Progress"}


@frappe.whitelist(methods=["POST"])
def mark_completed(task_instance):
    doc = frappe.get_doc("Scheduled Task Instance", task_instance, for_update=True)
    frappe.has_permission("Scheduled Task Instance", "write", doc=doc, throw=True)

    if doc.docstatus != 1:
        frappe.throw(_("Only submitted Task Instances can be marked Completed."))
    if doc.status not in ("Open", "In Progress"):
        frappe.throw(_("Only Open or In Progress Task Instances can be marked Completed."))

    doc.db_set("status", "Completed")
    if not doc.completed_date:
        doc.db_set("completed_date", frappe.utils.today())
    doc.add_comment("Comment", _("Task completed."))
    return {"status": "Completed"}
