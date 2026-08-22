# Copyright (c) 2026, afmcoltd
"""Switch on the two dated alerts whose shipped state cannot reach an existing site.

``import_file.ignore_values`` (frappe/modules/import_file.py:33) lists ``enabled`` for
Notification, so migrate NEVER copies that field onto a record that already exists — the
JSON decides it once, at creation, and after that only a person or a patch can move it.
A ``modified`` bump does not help: the field is excluded by name, not by timestamp.

Both warn that a dated document is about to lapse with money behind it, which is what
the other alerts in their group already do. Neither can nag: a Days Before alert selects
only the rows falling due on one calendar day, so each row is mailed once.

Runs once, and only lifts a record that is still off, so a site that switched it off
after this patch shipped keeps its choice.
"""

import frappe

ALERTS = (
    "Habitat - Rent Payment Due",
    "SIM Operations - Contract Expiry Soon",
)


def execute():
    """Enable each alert that still carries the shipped-off state."""
    for name in ALERTS:
        if not frappe.db.exists("Notification", name):
            continue
        if frappe.db.get_value("Notification", name, "enabled"):
            continue
        frappe.db.set_value("Notification", name, "enabled", 1)
