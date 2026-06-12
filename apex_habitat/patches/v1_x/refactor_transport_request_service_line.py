import frappe

# Legacy Workers/Representatives division values -> new transport-type service_line.
# 'Workers' is disambiguated below by request_type (an inter-city relocation keeps its
# own transport type); 'Representatives' was always the administrative document trip
# (gov item 62), submitted as a transport request, so it stays a transport request.
_REPRESENTATIVES = "Representatives"
_WORKERS = "Workers"
_ADMINISTRATIVE_TRIP = "Administrative Trip"
_INTER_CITY_RELOCATION = "Inter-City Relocation"
_SITE_TRANSPORT = "Site Transport"

# The legacy request_type that, for a 'Workers' row, maps to the Inter-City
# Relocation transport type rather than the default Site Transport.
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

    # Guard: nothing to do unless at least one legacy value is still present. This is
    # what makes the patch a clean no-op on fresh installs and on every re-run.
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
        # update_modified=False: a value remap is not a business edit and must not
        # disturb modified/modified_by or trip-the standard-JSON migrate-skip.
        frappe.db.set_value(
            "Transport Request",
            row.name,
            "service_line",
            new_value,
            update_modified=False,
        )

    frappe.db.commit()
