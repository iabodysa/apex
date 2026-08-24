# Copyright (c) 2026, afmcoltd

import json
import pathlib

import frappe


def execute():
    app_root = pathlib.Path(frappe.get_app_path("apex"))

    roleless = set()
    for path in app_root.rglob("workspace/*/*.json"):
        try:
            data = json.loads(path.read_text())
        except (ValueError, OSError):
            continue
        if data.get("doctype") != "Workspace" or not data.get("public"):
            continue
        if not (data.get("roles") or []):
            roleless.add(data.get("name"))

    if not roleless:
        return

    for name in sorted(roleless):
        if not frappe.db.exists("Workspace", name):
            continue
        if not frappe.db.exists("Has Role", {"parenttype": "Workspace", "parent": name}):
            continue
        frappe.db.delete("Has Role", {"parenttype": "Workspace", "parent": name})
        print(f"apex: cleared seeded roles on Workspace {name}")

    frappe.clear_cache()
