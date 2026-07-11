"""A-028: rename the two 'Stop' DocTypes to 'Suspension'.

English 'Stop' (=take out of service) collided with the route-waypoint
sense (Route Stop). 'Suspension' disambiguates. AR labels are unchanged.

pre_model_sync — MUST run before sync_all, else sync recreates an empty new-named
table beside the real data (the deadly trap; same pattern as rename_doctypes_b7).
rename_doc(force=True) renames the table AND fixes DocField.options / links / any
Property Setter in the DB; the on-disk JSON (already carrying the new name) is then
re-imported by migrate. Idempotent: skips a pair already renamed or absent.
"""

import frappe

RENAMES = [
    ("Driver Stop", "Driver Suspension"),
    ("Vehicle Stop", "Vehicle Suspension"),
]


def execute():
    for old, new in RENAMES:
        if frappe.db.exists("DocType", new):
            continue
        if not frappe.db.exists("DocType", old):
            continue
        frappe.rename_doc("DocType", old, new, force=True)
        frappe.db.commit()
