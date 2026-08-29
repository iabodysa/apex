# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe


LEGACY_DOCTYPE = "Wash Platform"
TARGET_DOCTYPE = "Service Platform"
CARRIED_FIELDS = ("provider", "status", "notes")
LEGACY_LINK_FIELDS = (("Wash Request", "wash_platform"),)
LINK_FIELDS = (
    ("Fuel Request", "fuel_platform"),
    ("Fuel Daily Log", "fuel_platform"),
    *LEGACY_LINK_FIELDS,
)


def execute():
    if not frappe.db.exists("DocType", TARGET_DOCTYPE):
        return

    _stamp_fuel_origin()

    if not frappe.db.exists("DocType", LEGACY_DOCTYPE):
        _assert_links_resolve()
        return

    legacy_before = frappe.db.count(LEGACY_DOCTYPE)
    moved = _move_wash_rows()
    _repoint_renamed(moved)
    _assert_every_row_landed(legacy_before, moved)
    _assert_links_resolve()


def _stamp_fuel_origin():
    for name in frappe.get_all(
        TARGET_DOCTYPE, filters={"service_type": ["in", ["", None]]}, pluck="name"
    ):
        frappe.db.set_value(
            TARGET_DOCTYPE, name, "service_type", "Fuel", update_modified=False
        )


def _target_name(original):
    occupant = frappe.db.get_value(TARGET_DOCTYPE, original, "service_type")
    if occupant in (None, "Wash"):
        return original
    candidate = f"{original} (Wash)"
    index = 2
    while frappe.db.get_value(TARGET_DOCTYPE, candidate, "service_type") == "Fuel":
        candidate = f"{original} (Wash {index})"
        index += 1
    return candidate


def _move_wash_rows():
    moved = {}
    for row in frappe.get_all(
        LEGACY_DOCTYPE,
        fields=["name", "owner", "creation", "modified", "modified_by", *CARRIED_FIELDS],
        order_by="creation asc",
    ):
        target = _target_name(row.name)
        moved[row.name] = target
        if frappe.db.exists(TARGET_DOCTYPE, target):
            continue
        frappe.get_doc(
            {
                "doctype": TARGET_DOCTYPE,
                "name": target,
                "platform_name": target,
                "service_type": "Wash",
                "owner": row.owner,
                "creation": row.creation,
                "modified": row.modified,
                "modified_by": row.modified_by,
                **{field: row.get(field) for field in CARRIED_FIELDS},
            }
        ).db_insert()
    return moved


def _repoint_renamed(moved):
    for old, new in moved.items():
        if old == new:
            continue
        for doctype, fieldname in LEGACY_LINK_FIELDS:
            if frappe.db.table_exists(doctype):
                frappe.db.set_value(
                    doctype, {fieldname: old}, fieldname, new, update_modified=False
                )


def _assert_every_row_landed(legacy_before, moved):
    landed = frappe.db.count(TARGET_DOCTYPE, {"service_type": "Wash"})
    if landed < legacy_before:
        frappe.throw(
            f"{landed} of {legacy_before} {LEGACY_DOCTYPE} rows reached "
            f"{TARGET_DOCTYPE}; migration stopped."
        )
    lost = sorted(
        target for target in moved.values() if not frappe.db.exists(TARGET_DOCTYPE, target)
    )
    if lost:
        frappe.throw(
            f"{TARGET_DOCTYPE} rows missing after the merge: {', '.join(lost[:20])}"
        )


def _assert_links_resolve():
    dangling = []
    for doctype, fieldname in LINK_FIELDS:
        if not frappe.db.table_exists(doctype):
            continue
        for value in frappe.get_all(
            doctype, filters={fieldname: ["is", "set"]}, pluck=fieldname, distinct=True
        ):
            if not frappe.db.exists(TARGET_DOCTYPE, value):
                dangling.append(f"{doctype}.{fieldname}={value}")
    if dangling:
        frappe.throw(
            f"{TARGET_DOCTYPE} links left dangling: {', '.join(sorted(dangling)[:20])}"
        )
