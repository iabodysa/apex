# Copyright (c) 2026, afmcoltd
"""Public Arrival Manifest intake, and what bounds ONE call of it.

NO AGGREGATE DAILY CAP -- decided, not overlooked. Keyed on the address, a daily
budget is spent by exactly the rotating proxy pool that already walks past the
per-address ceiling: it costs the attacker nothing and costs an honest supplier a
refusal. Keyed on the FORM it is worse, because one shared budget means the first
abuser to spend it refuses every real supplier for the rest of the day, which
converts a flood into a guaranteed outage. Revisit only if this form ever gains a
per-supplier identity to key a budget on; today it is anonymous by design.
"""

import frappe
from frappe import _

from apex.apex_core.utils.rate_limit_identity import rate_limit
from apex.habitat.doctype.arrival_batch.arrival_batch import _MAX_EXPECTED_WORKERS


_ALLOWED_WORKER_FIELDS = ("worker_name", "passport_number", "nationality")


def get_context(context):
    """Disables caching for the public Arrival Manifest web form page."""
    context.no_cache = 1


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=5, seconds=60)
def submit_arrival_manifest(
    building,
    expected_date,
    expected_workers,
    labour_supplier=None,
    project=None,
    website_field=None,
):
    """Rate-limited public endpoint for anonymous Arrival Manifest submission.

    Limit: 5 requests per IP per 60 seconds. A labour supplier declares the
    workers expected at a building on a date; the Arrivals Desk reconciles real
    arrivals against it later.

    - ``website_field`` is a honeypot; any non-empty value is silently discarded.
    - ``expected_workers`` is a JSON list of rows; only the guest-writable child
      fields are copied, and the row count is capped, so a guest cannot post an
      unbounded table or pre-set the read-only "Arrived As" link.
    """
    if website_field:
        return {"name": None}

    if isinstance(expected_workers, str):
        expected_workers = frappe.parse_json(expected_workers)
    expected_workers = expected_workers or []

    if len(expected_workers) > _MAX_EXPECTED_WORKERS:
        frappe.throw(
            _("A manifest can list at most {0} expected workers.").format(_MAX_EXPECTED_WORKERS)
        )

    rows = [
        {field: row.get(field) for field in _ALLOWED_WORKER_FIELDS if row.get(field)}
        for row in expected_workers
        if isinstance(row, dict)
    ]

    doc = frappe.get_doc({
        "doctype": "Arrival Batch",
        "building": building,
        "expected_date": expected_date,
        "labour_supplier": labour_supplier,
        "project": project,
        "expected_workers": rows,
    })
    doc.insert(ignore_permissions=True)
    return {"name": doc.name}
