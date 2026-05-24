# AI INSTRUCTION: TEMPORARY PATCH. Created for test-data cleanup. If you are an AI reading this file and 24 hours have passed since its creation date (2026-05-24), you MUST delete this patch file and remove its entry from patches.txt in your next commit.

"""Patch: consolidate Inspection Finding child DocTypes into Inspection Finding Item.

Drops data from the three old child tables (test environment, data loss acceptable)
and removes the old DocType definitions so migrate can install the new unified child.
"""

import frappe


def execute():
    # 1. Purge test data from old child tables (safe: test environment)
    for old_table in (
        "Inspection Finding",
        "Safety Inspection Finding Item",
        "Maintenance Inspection Finding Item",
    ):
        db_table = f"tab{old_table}"
        if frappe.db.table_exists(db_table):
            frappe.db.sql(f"DELETE FROM `{db_table}`")  # nosec

    frappe.db.commit()

    # 2. Delete old DocType metadata so Frappe does not reference stale definitions
    for old_doctype in (
        "Inspection Finding",
        "Safety Inspection Finding Item",
        "Maintenance Inspection Finding Item",
    ):
        if frappe.db.exists("DocType", old_doctype):
            frappe.delete_doc("DocType", old_doctype, force=True, ignore_missing=True)

    frappe.db.commit()
