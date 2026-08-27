# Copyright (c) 2026, afmcoltd

import frappe

from apex.habitat.doctype.accommodation_ledger.accommodation_ledger import (
    RETIRED_UNIQUE_KEY_NAME,
)

LEDGERS = {
    "Accommodation Ledger": "apex.habitat.doctype.accommodation_ledger.accommodation_ledger",
    "Facility Asset Movement Ledger": "apex.habitat.doctype.facility_asset_movement_ledger.facility_asset_movement_ledger",
    "Maintenance Cost Ledger": "apex.habitat.doctype.maintenance_cost_ledger.maintenance_cost_ledger",
    "Fuel Consumption Ledger": "apex.salis.doctype.fuel_consumption_ledger.fuel_consumption_ledger",
    "Trip Boarding Ledger": "apex.salis.doctype.trip_boarding_ledger.trip_boarding_ledger",
}


def _drop_retired_accommodation_key():
    try:
        frappe.db.sql(
            "ALTER TABLE `tabAccommodation Ledger` DROP INDEX `{0}`".format(
                RETIRED_UNIQUE_KEY_NAME
            )
        )
    except Exception:
        pass


def execute():
    _drop_retired_accommodation_key()

    for doctype, module in LEDGERS.items():
        if "is_reversal" not in frappe.db.get_table_columns(doctype):
            continue
        frappe.db.sql(
            """
            UPDATE `tab{0}`
            SET is_reversal = 1
            WHERE reversal_of IS NOT NULL AND reversal_of != '' AND is_reversal = 0
            """.format(doctype)
        )
        frappe.get_attr(module + ".on_doctype_update")()
