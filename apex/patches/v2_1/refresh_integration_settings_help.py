# Copyright (c) 2026, AFMCO and contributors
"""Re-seed the read-only Apex Integration Settings help panels from the shipped text.

Those panels are documentation the app ships, not operator data, but they are
Text Editor fields with a ``default``: the default only seeds the Single the
first time it is written, so an upgraded site keeps whatever text the release it
was installed from stored in ``tabSingles``. The integration guidance has since
been corrected - a browser or store-installed client must never be handed an API
secret - and that correction reaches no existing site without this.

Idempotent: a field already carrying the shipped text is skipped, so a second
run writes nothing.
"""

import frappe

DOCTYPE = "Apex Integration Settings"
HELP_FIELDS = ("integration_help", "messaging_gateway_help")


def execute():
    meta = frappe.get_meta(DOCTYPE)
    for fieldname in HELP_FIELDS:
        field = meta.get_field(fieldname)
        if not field or not field.default:
            continue
        if frappe.db.get_single_value(DOCTYPE, fieldname, cache=False) == field.default:
            continue
        frappe.db.set_single_value(DOCTYPE, fieldname, field.default)
