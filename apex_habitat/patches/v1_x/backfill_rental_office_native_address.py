"""ONE-TIME backfill: create a native Frappe Address for each Rental Office that
has an inline `city` value and does not yet have a linked Address record.

T-532 adopts the native Frappe Address (Address DocType + Dynamic Link, the
ERPNext pattern) for Rental Office. This migrates the legacy inline `city` value
into a native Address so existing offices use the platform Address/Contact system.
Loses no data: `city` stays on the row; this only mirrors it into an Address.

Idempotency guards:
- Skips any office that already has an Address linked via Dynamic Link.
- Skips any office with no resolvable city value.
- Wrapped in a per-office savepoint so one failure does not abort the others.
- Safe to re-run: the existence check prevents duplicate Address creation.

PRUNE from patches.txt once every deployed site has run it (check tabPatch Log).
"""

from __future__ import annotations

import frappe


def execute():
    offices = frappe.db.get_all("Rental Office", fields=["name", "city"])

    if not offices:
        return

    created = 0
    skipped = 0

    for idx, office in enumerate(offices):
        already_linked = frappe.db.exists(
            "Dynamic Link",
            {
                "link_doctype": "Rental Office",
                "link_name": office.name,
                "parenttype": "Address",
            },
        )
        if already_linked:
            skipped += 1
            continue

        city_val = (office.city or "").strip()
        if not city_val:
            skipped += 1
            continue

        # Index-based, guaranteed SQL-safe identifier — a doc-name-derived name can
        # contain spaces/parentheses/non-ASCII that break the savepoint SQL.
        savepoint = f"bfill_rental_office_addr_{idx}"
        try:
            frappe.db.savepoint(savepoint)

            addr = frappe.get_doc(
                {
                    "doctype": "Address",
                    "address_title": f"{office.name} — {city_val}",
                    "address_type": "Office",
                    "address_line1": city_val,
                    "city": city_val,
                    "links": [
                        {
                            "link_doctype": "Rental Office",
                            "link_name": office.name,
                        }
                    ],
                }
            )
            addr.insert(ignore_permissions=True)  # audit-ok — admin patch, no user context
            created += 1

        except Exception:
            frappe.db.rollback(save_point=savepoint)
            frappe.log_error(
                title=f"backfill_rental_office_native_address: skipped {office.name}",
                message=frappe.get_traceback(),
            )
            skipped += 1
        else:
            frappe.db.release_savepoint(savepoint)

    frappe.logger().info(
        f"backfill_rental_office_native_address: created={created}, skipped={skipped}"
    )
