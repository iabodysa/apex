# Copyright (c) 2026, afmcoltd

import frappe

from apex.habitat.temporary_worker_engine import repoint_party


def execute():
    if not frappe.db.table_exists("Temporary Worker"):
        return

    for tw in frappe.get_all(
        "Temporary Worker",
        filters={"status": "Linked", "linked_employee": ["is", "set"]},
        fields=["name", "linked_employee"],
    ):
        repoint_party(tw.name, tw.linked_employee)
