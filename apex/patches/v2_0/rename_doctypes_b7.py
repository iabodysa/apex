"""V2-B7 (P-161): rename 16 DocTypes to drop the redundant module prefix.

pre_model_sync — MUST run before sync_all, else sync recreates an empty new-named
table beside the real data (the deadly trap; matrix §0). rename_doc(force=True)
renames the table AND fixes tabUser Permission.allow / DocField.options / Property
Setter / links in the DB; the on-disk JSON (already carrying the new name) is then
re-imported by migrate. Idempotent: skips a pair already renamed or absent.

Council name overrules applied (matrix section 12): Accommodation Assignment ->
Housing Assignment (not bare "Assignment" = frappe's Task); Accommodation Checkout
-> Housing Checkout (not bare "Checkout" = erpnext POS). Heavy Building last.
"""

import frappe

# [#ttd4lk]
RENAMES = [
    ("Accommodation Bed", "Bed"),
    ("Accommodation Checkout", "Housing Checkout"),
    ("Accommodation Floor Plan", "Floor Plan"),
    ("Accommodation Lease", "Lease"),
    ("Accommodation Occupancy Snapshot", "Occupancy Snapshot"),
    ("Accommodation QR Location", "QR Location"),
    ("Accommodation Resident Request", "Resident Request"),
    ("Accommodation Room", "Room"),
    ("Accommodation Site", "Site"),
    ("Client Audit Remediation Plan", "Audit Remediation Plan"),
    ("Non-Financial Depreciation Snapshot", "Operational Depreciation Snapshot"),
    ("Habitat Safety Incident", "Safety Incident"),
    ("Salis Portal Theme", "Driver Portal Theme"),
    ("Manifest Passenger", "Passenger Manifest Item"),
    ("Accommodation Assignment", "Housing Assignment"),
    ("Accommodation Building", "Building"),  # [#ka38nf]
]


def execute():
    for old, new in RENAMES:
        if frappe.db.exists("DocType", new):
            continue  # [#3562qx]
        if not frappe.db.exists("DocType", old):
            continue  # [#28qx78]
        frappe.rename_doc("DocType", old, new, force=True)
        frappe.db.commit()  # [#c9uohc]
