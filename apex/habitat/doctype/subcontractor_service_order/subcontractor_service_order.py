# Copyright (c) 2026, AFMCO and contributors
"""Subcontractor Service Order controller.

Why Finance Manager holds a permlevel-1 row here and NO permlevel-0 row.
It is a deliberate field overlay, not an omission: the role may read and set
``service_cost`` on an order that Accommodation Manager opens, and may not open,
create, submit or cancel it. Document access is resolved from permlevel-0 rows only,
field access is resolved separately and unions every permlevel across the user's roles,
so the two are independent grants -- the row activates the moment one user holds both
roles, with no DocPerm edit. No shipped role profile bundles them today, so this
overlay is dormant until an administrator does. Proof and the framework citations are
in
``apex/habitat/doctype/custody_damage_assessment/test_finance_manager_field_overlay.py``.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, nowdate


class SubcontractorServiceOrder(Document):
    pass


def before_save(doc, method=None):
    if not doc.company:
        from apex.apex_core.doctype.habitat_settings.habitat_settings import get_default_company
        doc.company = get_default_company()


@frappe.whitelist(methods=["POST"])
def start_work(service_order):
    """Transition Subcontractor Service Order from Scheduled to In Progress."""
    doc = frappe.get_doc("Subcontractor Service Order", service_order)
    frappe.has_permission("Subcontractor Service Order", "write", doc=doc, throw=True)

    if doc.docstatus != 1:
        frappe.throw(_("Only submitted Service Orders can be started."))
    if doc.status != "Scheduled":
        frappe.throw(_("Only Service Orders with status Scheduled can be marked In Progress."))

    doc.db_set("status", "In Progress")
    doc.add_comment("Comment", _("Work started — status set to In Progress."))
    return {"status": "In Progress"}


@frappe.whitelist(methods=["POST"])
def mark_completed(
    service_order,
    supervisor_confirmed=None,
    completion_photo=None,
    visit_notes=None,
    actual_visit_date=None,
):
    """Transition Subcontractor Service Order from In Progress to Completed, and
    record the visit evidence in the same call.

    Controlled completion gate mirroring start_work / mark_missed: only a submitted
    order that is In Progress may be marked Completed, so the terminal state is
    reached through a guarded chokepoint rather than a free-form status edit.

    The four evidence fields travel with this method for the reason
    ``maintenance_work_order.mark_completed`` records: they are filled once the order
    is SUBMITTED and In Progress, none is ``allow_on_submit``, and widening them would
    not be enough anyway — saving a submitted document is ``update_after_submit``,
    which Frappe gates on the SUBMIT permission
    (``frappe/model/document.py:905-906``), while the supervisor doing the visit holds
    write. Granting submit to reach a notes box would also hand them authority to
    submit and cancel the order they are executing. ``db_set`` is therefore their only
    writer at docstatus 1; permission is re-checked above because ``db_set`` goes
    straight to the database. Each field is written only when supplied, so a caller
    that passes none behaves exactly as before."""
    doc = frappe.get_doc("Subcontractor Service Order", service_order)
    frappe.has_permission("Subcontractor Service Order", "write", doc=doc, throw=True)

    if doc.docstatus != 1:
        frappe.throw(_("Only submitted Service Orders can be marked Completed."))
    if doc.status != "In Progress":
        frappe.throw(_("Only Service Orders with status In Progress can be marked Completed."))

    evidence = {
        "supervisor_confirmed": cint(supervisor_confirmed) if supervisor_confirmed is not None else None,
        "completion_photo": completion_photo,
        "visit_notes": visit_notes,
        "actual_visit_date": actual_visit_date,
    }
    for fieldname, value in evidence.items():
        if value is not None:
            doc.db_set(fieldname, value)

    doc.db_set("status", "Completed")
    doc.add_comment("Comment", _("Marked Completed via controlled method."))
    return {"status": "Completed"}


@frappe.whitelist(methods=["POST"])
def mark_missed(service_order):
    """Transition Subcontractor Service Order from In Progress to Missed."""
    doc = frappe.get_doc("Subcontractor Service Order", service_order)
    frappe.has_permission("Subcontractor Service Order", "write", doc=doc, throw=True)

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
