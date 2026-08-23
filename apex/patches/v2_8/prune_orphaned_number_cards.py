# Copyright (c) 2026, afmcoltd
"""Remove a Number Card row whose shipped file is gone.

``sync_all`` upserts a standard record from its file and never prunes one whose file has
been deleted (frappe/model/sync.py:125-140), so a Number Card removed from
``apex/**/number_card`` still sits in ``tabNumber Card`` on every site that migrated
before the deletion, and still answers a dashboard or workspace that links it by name.

Only rows this app shipped are swept: ``is_standard=1`` restricts to file-synced records
and ``module`` scopes to Apex's own modules, so a card an operator built by hand in the
desk carries no shipped directory and is never touched. The shipped set is read off disk
rather than listed here, so this stays correct as cards come and go.
"""

import json
import pathlib

import frappe

APEX_MODULES = ["Habitat", "Salis", "Apex Core", "Logistay"]


def execute():
    """Delete standard Number Card rows in Apex's modules whose shipped file is gone."""
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
