"""Scheduled Task Instance controller."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


class ScheduledTaskInstance(Document):
    pass


def on_doctype_update():
    """Hard idempotency backstop: a composite UNIQUE index on ``(template,
    due_date, docstatus)`` so ``habitat.tasks.daily_scheduled_task_instance_generator``
    cannot create two instances for the same template+period even if its
    check-then-insert is bypassed by a race.

    Column choice: the generator's guard is
    ``exists({template, due_date, docstatus != 2})`` — i.e. it treats Draft(0)
    and Submitted(1) as the blocking set but lets a new instance be created after
    the prior one is Cancelled(2). ``docstatus`` is therefore part of the key:
    including it keeps a cancelled instance (and an amendment, which reuses the
    template+due_date of its cancelled original) from colliding with a fresh
    Open instance, while still blocking the duplicate Drafts the generator could
    otherwise race-insert (it only ever inserts at docstatus 0). Guarded so
    pre-existing duplicate data logs rather than aborting migrate."""
    from apex_habitat.habitat.utils.ledger_index import add_unique_guarded

    add_unique_guarded(
        "Scheduled Task Instance",
        ["template", "due_date", "docstatus"],
        constraint_name="unique_sti_template_due_status",
    )


def validate(doc, method=None):
    if not doc.due_date:
        frappe.throw(_("Due Date is required."))


def on_submit(doc, method=None):
    # Submitting activates the task; it stays Open until a worker starts it.
    # (Previously this forced "Completed", which made start_task unreachable.)
    if doc.status not in ("In Progress", "Completed", "Cancelled"):
        doc.db_set("status", "Open")


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


@frappe.whitelist(methods=["POST"])
def mark_completed(task_instance):
    """Transition Scheduled Task Instance from Open/In Progress to Completed."""
    if not frappe.has_permission("Scheduled Task Instance", "write"):
        frappe.throw(_("Not permitted"), frappe.PermissionError)

    doc = frappe.get_doc("Scheduled Task Instance", task_instance)

    if doc.docstatus != 1:
        frappe.throw(_("Only submitted Task Instances can be marked Completed."))
    if doc.status not in ("Open", "In Progress"):
        frappe.throw(_("Only Open or In Progress Task Instances can be marked Completed."))

    doc.db_set("status", "Completed")
    doc.add_comment("Comment", _("Task completed."))
    return {"status": "Completed"}
