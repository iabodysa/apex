# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe import _

_ITEM_FIELDS = [
    "name",
    "item_name",
    "item_category",
    "uom",
    "room",
    "expected_quantity",
    "counted_quantity",
    "quantity_variance",
    "condition",
    "status",
    "notes",
    "last_count_date",
]

_WRITABLE = ("counted_quantity", "condition", "notes")

COUNT_LINE_LIMIT = 200


def _condition_options():
    df = frappe.get_meta("Housing Inventory").get_field("condition")
    options = (df.options or "") if df else ""
    return [o for o in options.split("\n") if o]


@frappe.whitelist()
def get_inventory_for_building(building, room=None):
    frappe.has_permission("Housing Inventory", "read", throw=True)
    if not building:
        frappe.throw(_("A building is required to load the inventory."))

    filters = {"building": building}
    if room:
        filters["room"] = room

    items = frappe.get_list(
        "Housing Inventory",
        filters=filters,
        fields=_ITEM_FIELDS,
        order_by="room asc, item_name asc",
        limit_page_length=0,
    )

    room_names = sorted({it.room for it in items if it.room})
    labels = {}
    if room_names:
        for r in frappe.get_list(
            "Room",
            filters={"name": ["in", room_names]},
            fields=["name", "room_number"],
            limit_page_length=0,
        ):
            labels[r.name] = r.room_number or r.name
    for it in items:
        it["room_label"] = labels.get(it.room) if it.room else None
        it["item_label"] = _(it.item_name) if it.item_name else _("Inventory Item")

    return {
        "building": building,
        "items": items,
        "conditions": _condition_options(),
    }


@frappe.whitelist(methods=["POST"])
def submit_counts(building, lines):
    frappe.has_permission("Housing Inventory", "write", throw=True)

    if not building:
        frappe.throw(_("A building is required to submit counts."))

    try:
        lines = frappe.parse_json(lines)
    except ValueError:
        frappe.throw(_("Counts must be valid JSON."))
    if not isinstance(lines, list):
        frappe.throw(_("Counts must be a list."))
    if not lines:
        frappe.throw(_("No count lines to submit."))
    if len(lines) > COUNT_LINE_LIMIT:
        frappe.throw(
            _("Submit at most {0} count lines at a time. You sent {1}.").format(
                COUNT_LINE_LIMIT, len(lines)
            )
        )

    saved_rows = []
    errors = []
    for line in lines:
        name = line.get("name")
        if not name:
            errors.append({"name": None, "error": _("A line is missing its item.")})
            continue

        savepoint = "housing_count_" + frappe.scrub(name)
        frappe.db.savepoint(savepoint)
        try:
            doc = frappe.get_doc("Housing Inventory", name)
            if doc.building != building:
                frappe.throw(
                    _("Item {0} does not belong to this building.").format(name),
                    frappe.PermissionError,
                )

            if line.get("counted_quantity") is not None:
                doc.counted_quantity = frappe.utils.flt(line.get("counted_quantity"))
            if line.get("condition"):
                doc.condition = line.get("condition")
            if "notes" in line:
                doc.notes = line.get("notes")

            doc.save()
        except Exception as e:
            frappe.db.rollback(save_point=savepoint)
            errors.append({"name": name, "error": str(e)})
            continue
        else:
            frappe.db.release_savepoint(savepoint)
            doc.reload()
            saved_rows.append(
                {
                    "name": doc.name,
                    "item_name": doc.item_name,
                    "quantity_variance": doc.quantity_variance,
                    "last_count_date": doc.last_count_date,
                }
            )

    return {
        "ok": not errors,
        "saved": len(saved_rows),
        "failed": len(errors),
        "rows": saved_rows,
        "errors": errors,
    }
