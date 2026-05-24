"""Maintenance Material Template controller."""
import frappe
from frappe import _
from frappe.model.document import Document


class MaintenanceMaterialTemplate(Document):
    pass


@frappe.whitelist(methods=["POST"])
def load_template_into_doc(doctype, docname, issue_type):
    """Load the first active template matching issue_type into the doc's procurement_items.

    Safe: only appends rows. Never creates purchasing, stock, accounting, or payroll records.
    The caller (JS button) passes doctype = 'Maintenance Request' or 'Maintenance Work Order'.
    """
    if doctype not in ("Maintenance Request", "Maintenance Work Order"):
        frappe.throw(_("Template loading is only supported for Maintenance Request and Maintenance Work Order."))

    if not frappe.has_permission(doctype, "write"):
        frappe.throw(_("Not permitted"), frappe.PermissionError)

    templates = frappe.get_all(
        "Maintenance Material Template",
        filters={"issue_type": issue_type, "is_active": 1},
        fields=["name"],
        limit=1,
    )
    if not templates:
        return {"rows_added": 0, "message": f"No active template found for issue type: {issue_type}"}

    template = frappe.get_doc("Maintenance Material Template", templates[0].name)
    doc = frappe.get_doc(doctype, docname)

    if doc.docstatus != 0:
        frappe.throw(_("Template can only be loaded into a Draft document."))

    rows_added = 0
    for tpl_item in template.items:
        material = frappe.get_doc("Maintenance Material", tpl_item.material)
        doc.append("procurement_items", {
            "material": tpl_item.material,
            "item_description": material.material_name,
            "quantity": tpl_item.quantity or 1,
            "unit": tpl_item.unit or material.default_uom or "Piece",
        })
        rows_added += 1

    if rows_added:
        doc.requires_procurement = 1
    doc.save(ignore_permissions=True)
    return {"rows_added": rows_added, "template": template.name}
