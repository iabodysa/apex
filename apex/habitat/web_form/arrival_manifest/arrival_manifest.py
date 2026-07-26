# Copyright (c) 2026, AFMCO and contributors
import frappe
from frappe import _
from frappe.rate_limiter import rate_limit

# [#8g8lrm]
_MAX_EXPECTED_WORKERS = 500

# [#g4hzd4]
_ALLOWED_WORKER_FIELDS = ("worker_name", "passport_number", "nationality")


def get_context(context):
    context.no_cache = 1


@frappe.whitelist(allow_guest=True, methods=["POST"])
# No `key`: it was a form_dict lookup (rate_limiter.py:143) any caller could set from
# the query string, buying a private window per value. `ip_based` (default True) is
# what actually keys this window to the address (rate_limiter.py:110,141,147-150).
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
    # [#2pdod8]
    if website_field:
        return {"name": None}

    if isinstance(expected_workers, str):
        expected_workers = frappe.parse_json(expected_workers)
    expected_workers = expected_workers or []

    # [#r2d5pb]
    if len(expected_workers) > _MAX_EXPECTED_WORKERS:
        frappe.throw(
            _("A manifest can list at most {0} expected workers.").format(_MAX_EXPECTED_WORKERS)
        )

    # [#1zodbv]
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
    doc.insert(ignore_permissions=True)  # audit-ok — guest web-form intake, rate-limited + honeypot-guarded; field-allowlisted
    # [#jwr9pv]
    return {"name": doc.name}
