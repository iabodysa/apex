# Copyright (c) 2026, afmcoltd

import frappe


SOURCE = "Payment Routing Settings"
TARGET = "Habitat Settings"
FIELDS = ("target_payment_doctype", "auto_submit_target")

CHILD_DOCTYPE = "Payment Routing Field Map"
CHILD_FIELD = "field_map"


def execute():
    _carry_values()
    _carry_field_map()

    if frappe.db.exists("DocType", SOURCE):
        frappe.delete_doc("DocType", SOURCE, force=True)

    _clear_orphan_singles()


def _carry_values():
    source = frappe.db.get_singles_dict(SOURCE)
    target = frappe.db.get_singles_dict(TARGET)
    for field in FIELDS:
        if field not in source:
            continue
        if target.get(field) not in (None, ""):
            continue
        frappe.db.set_single_value(TARGET, field, source[field])


def _carry_field_map():
    if not frappe.db.table_exists(CHILD_DOCTYPE):
        return

    child = frappe.qb.DocType(CHILD_DOCTYPE)
    source_rows = {"parent": SOURCE, "parenttype": SOURCE, "parentfield": CHILD_FIELD}

    if frappe.db.exists(
        CHILD_DOCTYPE, {"parent": TARGET, "parenttype": TARGET, "parentfield": CHILD_FIELD}
    ):
        frappe.db.delete(CHILD_DOCTYPE, source_rows)
        return

    (
        frappe.qb.update(child)
        .set(child.parent, TARGET)
        .set(child.parenttype, TARGET)
        .where(
            (child.parent == SOURCE)
            & (child.parenttype == SOURCE)
            & (child.parentfield == CHILD_FIELD)
        )
    ).run()


def _clear_orphan_singles():
    frappe.db.delete("Singles", {"doctype": SOURCE})
