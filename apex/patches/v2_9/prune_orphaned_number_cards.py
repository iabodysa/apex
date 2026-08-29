# Copyright (c) 2026, afmcoltd

import json
import pathlib

import frappe

APEX_MODULES = ["Habitat", "Salis", "Apex Core", "Logistay"]


def execute():
    app_root = pathlib.Path(frappe.get_app_path("apex"))

    shipped = set()
    for path in app_root.rglob("number_card/*/*.json"):
        if path.stem != path.parent.name:
            continue
        try:
            data = json.loads(path.read_text())
        except (ValueError, OSError):
            continue
        if data.get("doctype") == "Number Card" and data.get("name"):
            shipped.add(data["name"])

    if not shipped:
        return

    orphans = frappe.get_all(
        "Number Card",
        filters={
            "module": ["in", APEX_MODULES],
            "is_standard": 1,
            "name": ["not in", sorted(shipped)],
        },
        pluck="name",
    )
    for name in orphans:
        frappe.delete_doc("Number Card", name, ignore_missing=True, force=True)
