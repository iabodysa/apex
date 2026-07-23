# Copyright (c) 2026, AFMCO and contributors
import frappe


def execute():
    """Backfill total_rooms / total_floors on existing Accommodation Building rows.

    The controller now derives both from the generated rooms (in before_save and
    immediately after room generation), but buildings saved before that change show
    stale 0 / blank values. Recompute once for every existing building. Idempotent.
    """
    for name in frappe.get_all("Building", pluck="name"):
        total_rooms = frappe.db.count("Room", {"building": name})
        floor_values = frappe.db.get_all(
            "Room", filters={"building": name}, pluck="floor", distinct=True
        )
        total_floors = len([f for f in floor_values if f is not None])
        frappe.db.set_value(
            "Building",
            name,
            {"total_rooms": total_rooms, "total_floors": total_floors},
            update_modified=False,
        )
