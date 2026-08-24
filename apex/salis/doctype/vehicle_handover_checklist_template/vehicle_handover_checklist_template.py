# Copyright (c) 2026, afmcoltd

import frappe
from frappe import _
from frappe.model.document import Document


class VehicleHandoverChecklistTemplate(Document):
    pass


@frappe.whitelist(methods=["POST"])
def load_template_into_doc(handover, template):
    doc = frappe.get_doc("Vehicle Handover", handover)
    frappe.has_permission("Vehicle Handover", "write", doc=doc, throw=True)

    if doc.docstatus != 0:
        frappe.throw(_("Checklist template can only be loaded into a Draft handover."))

    tpl = frappe.get_doc("Vehicle Handover Checklist Template", template)
    if not tpl.is_active:
        frappe.throw(_("Checklist template {0} is not active.").format(tpl.name))

    rows_added = 0
    for tpl_item in tpl.items:
        doc.append(
            "handover_check_items",
            {"check_item": tpl_item.check_item, "remark": tpl_item.remark or ""},
        )
        rows_added += 1

    if rows_added:
        try:
            doc.save()
        except Exception:
            frappe.db.rollback()
            frappe.throw(_("Could not save changes. Please try again or contact support."))

    return {"rows_added": rows_added, "template": tpl.name}
