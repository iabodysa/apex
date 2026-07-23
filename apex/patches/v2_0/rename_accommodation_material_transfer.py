"""T-033: shorten 'Accommodation Material Transfer' to the concise 'Material Transfer'.

The 'Accommodation' prefix was redundant: no other 'Material Transfer' DocType exists
in the app (ERPNext's material-transfer DocType is named 'Stock Entry'), so the shorter
name stays unambiguous. Renames the parent and its child table.

pre_model_sync — MUST run before sync_all, else sync recreates an empty new-named table
beside the real data (same trap as rename_stop_doctypes_to_suspension). rename_doc
(force=True) renames the table AND fixes DocField.options / links / Property Setters in
the DB; the on-disk JSON (already carrying the new name) is then re-imported by migrate.
Idempotent: skips a pair already renamed or absent.
"""

import frappe

RENAMES = [
    ("Accommodation Material Transfer", "Material Transfer"),
    ("Accommodation Material Transfer Item", "Material Transfer Item"),
]


def execute():
    for old, new in RENAMES:
        if frappe.db.exists("DocType", new):
            continue
        if not frappe.db.exists("DocType", old):
            continue
        frappe.rename_doc("DocType", old, new, force=True)
        frappe.db.commit()
