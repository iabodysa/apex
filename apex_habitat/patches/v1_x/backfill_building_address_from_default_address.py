# Copyright (c) 2026, AFMCO and contributors
"""ONE-TIME backfill: set Accommodation Building.building_address from the building's
legacy default native Address (linked via Dynamic Link) when the field is still empty.

Earlier rows linked an Address to the building via Dynamic Link but never populated the
``building_address`` Link field the controller now reads (get_site_address, T-144). This
resolves each building's default Address and writes it into the empty field.

Idempotency guards:
- Skips any building that already has a ``building_address`` (never clobbers a value).
- Skips any building whose default Address does not resolve (a building may legitimately
  have no Address — that is not an error).
- Writes via frappe.db.set_value (update_modified=False) to avoid full save/validation
  churn on historical rows.
- Safe to re-run and a no-op on fresh installs.

PRUNE from patches.txt once every deployed site has run it (check tabPatch Log).
"""

from __future__ import annotations

import frappe

_DOCTYPE = "Accommodation Building"


def execute():
    # Resolver from the native Address DocType; returns an Address name or None.
    from frappe.contacts.doctype.address.address import get_default_address

    # Only consider rows where the target field is unset — keeps the backfill scoped
    # and the loop a no-op once every building already carries its address.
    buildings = frappe.get_all(
        _DOCTYPE,
        filters={"building_address": ["in", [None, ""]]},
        pluck="name",
    )
    if not buildings:
        return

    updated = 0
    skipped = 0

    for name in buildings:
        default_address = get_default_address(_DOCTYPE, name)
        # No resolvable default Address -> leave the building untouched (legitimate).
        if not default_address:
            skipped += 1
            continue

        frappe.db.set_value(
            _DOCTYPE, name, "building_address", default_address, update_modified=False
        )
        updated += 1

    frappe.logger().info(
        f"backfill_building_address_from_default_address: updated={updated}, skipped={skipped}"
    )
