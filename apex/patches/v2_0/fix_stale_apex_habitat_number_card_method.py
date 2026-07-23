# Copyright (c) 2026, AFMCO and contributors
import frappe

# Sites migrated before the app was renamed apex_habitat -> apex keep Number Card
# rows whose `method` still points at the dead module path
# `apex_habitat.habitat.api.dashboard.*`. The committed JSON is correct, but these
# rows were seeded once and never re-synced, so opening the dashboard raises
# "App apex_habitat is not installed / failed to get method". Rewrite the dead
# prefix in place. Idempotent + a no-op on fresh installs (no matching rows).


def execute():
    # A literal substring test, not a LIKE filter: Frappe's ORM does not honour an
    # escaped underscore (r"apex\_habitat"), and an unescaped one matches the healthy
    # "apex.habitat" too. Fetch every method and rewrite only the dead literal prefix.
    for card in frappe.get_all("Number Card", fields=["name", "method"]):
        method = card.method or ""
        if "apex_habitat." not in method:
            continue
        frappe.db.set_value(
            "Number Card",
            card.name,
            "method",
            method.replace("apex_habitat.", "apex."),
            update_modified=False,
        )
