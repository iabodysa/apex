# Copyright (c) 2026, AFMCO and contributors
"""ONE-TIME backfill: create a native Frappe Address for each Accommodation Site
that has a city or district value and does not yet have a linked Address record.

Idempotency guards:
- Skips any site that already has an Address linked via Dynamic Link.
- Wrapped in a per-site savepoint so one failure does not abort the others.
- Safe to re-run: existence check prevents duplicate Address creation.

PRUNE from patches.txt once every deployed site has run it (check tabPatch Log).
"""

from __future__ import annotations

import frappe


def execute():
    sites = frappe.db.get_all(
        "Accommodation Site",
        fields=["name", "city", "district"],
    )

    if not sites:
        return

    created = 0
    skipped = 0

    for site in sites:
        # [#kurcce]
        already_linked = frappe.db.exists(
            "Dynamic Link",
            {
                "link_doctype": "Accommodation Site",
                "link_name": site.name,
                "parenttype": "Address",
            },
        )
        if already_linked:
            skipped += 1
            continue

        # [#iffmq8]
        city_val = (site.city or "").strip()
        district_val = (site.district or "").strip()
        if not city_val and not district_val:
            skipped += 1
            continue

        savepoint = f"bfill_site_addr_{frappe.scrub(site.name)}"
        try:
            frappe.db.savepoint(savepoint)

            # [#m52vzj]
            title_parts = [site.name]
            if city_val:
                title_parts.append(city_val)
            address_title = " — ".join(title_parts)

            addr = frappe.get_doc(
                {
                    "doctype": "Address",
                    "address_title": address_title,
                    "address_type": "Office",
                    # [#q0xkyw]
                    "address_line1": district_val or city_val,
                    # city field on Address DocType: City name (plain text accepted by Frappe).
                    "city": city_val or district_val,
                    "links": [
                        {
                            "link_doctype": "Accommodation Site",
                            "link_name": site.name,
                        }
                    ],
                }
            )
            addr.insert(ignore_permissions=True)  # audit-ok — admin patch, no user context
            created += 1

        except Exception:
            frappe.db.rollback(save_point=savepoint)
            frappe.log_error(
                title=f"backfill_accommodation_site_native_address: skipped {site.name}",
                message=frappe.get_traceback(),
            )
            skipped += 1
        else:
            frappe.db.release_savepoint(savepoint)

    frappe.logger().info(
        f"backfill_accommodation_site_native_address: created={created}, skipped={skipped}"
    )
