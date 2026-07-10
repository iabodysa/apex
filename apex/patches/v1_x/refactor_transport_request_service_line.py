# Copyright (c) 2026, AFMCO and contributors
import frappe

# [#eapxvv]
_REPRESENTATIVES = "Representatives"
_WORKERS = "Workers"
_ADMINISTRATIVE_TRIP = "Administrative Trip"
_INTER_CITY_RELOCATION = "Inter-City Relocation"
_SITE_TRANSPORT = "Site Transport"

# [#73g7i7]
_INTER_CITY_REQUEST_TYPE = "Inter-City Relocation"


def execute():
    """Remap Transport Request.service_line from the retired Workers/Representatives
    division onto the transport-type model.

    Mapping:
      * ``Representatives`` -> ``Administrative Trip`` (gov item 62 — document /
        administrative trips; they were submitted as transport requests).
      * ``Workers`` -> ``Inter-City Relocation`` when the row's ``request_type`` is an
        inter-city relocation, otherwise ``Site Transport`` (accommodation->site
        shuttle). This keeps service_line consistent with the preserved request_type.

    Idempotent and a no-op on fresh installs / on re-run: it only ever touches rows
    that still physically hold a legacy value, and the new values are never legacy,
    so a second pass matches nothing. Reads/writes go through ``frappe.db`` directly
    (not the ORM/Select validation) because the legacy strings are no longer valid
    Select options once the model JSON has synced.
    """
    if not frappe.db.table_exists("Transport Request"):
        return

    # [#nkgab9]
    legacy_rows = frappe.db.get_all(
        "Transport Request",
        filters={"service_line": ["in", [_WORKERS, _REPRESENTATIVES]]},
        fields=["name", "service_line", "request_type"],
    )
    if not legacy_rows:
        return

    for row in legacy_rows:
        if row.service_line == _REPRESENTATIVES:
            new_value = _ADMINISTRATIVE_TRIP
        elif row.request_type == _INTER_CITY_REQUEST_TYPE:
            new_value = _INTER_CITY_RELOCATION
        else:
            new_value = _SITE_TRANSPORT
        # [#m4p8nq]
        frappe.db.set_value(
            "Transport Request",
            row.name,
            "service_line",
            new_value,
            update_modified=False,
        )

    frappe.db.commit()
