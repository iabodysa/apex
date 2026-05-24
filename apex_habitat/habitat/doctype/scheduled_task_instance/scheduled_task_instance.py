"""Scheduled Task Instance controller."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


class ScheduledTaskInstance(Document):
    pass


def validate(doc, method=None):
    if not doc.due_date:
        frappe.throw(_("Due Date is required."))


def on_submit(doc, method=None):
    doc.db_set("status", "Completed")


def before_cancel(doc, method=None):
    if not doc.cancellation_reason:
        frappe.throw(_("Cancellation Reason is required before cancelling a Scheduled Task Instance."))


@frappe.whitelist(methods=["POST"])
def start_task(task_instance):
    """Transition Scheduled Task Instance from Open to In Progress."""
    if not frappe.has_permission("Scheduled Task Instance", "write"):
        frappe.throw(_("Not permitted"), frappe.PermissionError)

    doc = frappe.get_doc("Scheduled Task Instance", task_instance)

    if doc.docstatus != 1:
        frappe.throw(_("Only submitted Task Instances can be started."))
    if doc.status != "Open":
        frappe.throw(_("Only Task Instances with status Open can be marked In Progress."))

    doc.db_set("status", "In Progress")
    doc.add_comment("Comment", _("Task started — status set to In Progress."))
    return {"status": "In Progress"}
