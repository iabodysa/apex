# Copyright (c) 2026, AFMCO and contributors
import frappe
from frappe import _
from frappe.rate_limiter import rate_limit

# Mirror the controller cap so the public endpoint rejects an oversized table
# before it ever reaches insert.
_MAX_EXPECTED_WORKERS = 500

# Only these child fields are guest-writable. "temporary_worker" (Arrived As) is
# read-only by design - it is set by the Arrivals Desk during reconciliation, so
# a guest must never be able to seed it.
_ALLOWED_WORKER_FIELDS = ("worker_name", "passport_number", "nationality")


def get_context(context):
    context.no_cache = 1


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(key="frappe.request.remote_addr", limit=5, seconds=60)
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
    # [#armp01] honeypot: a bot filling the hidden field is dropped, not stored.
    if website_field:
        return {"name": None}

    if isinstance(expected_workers, str):
        expected_workers = frappe.parse_json(expected_workers)
    expected_workers = expected_workers or []

    # [#armp02] cap before building rows so a huge payload fails fast.
    if len(expected_workers) > _MAX_EXPECTED_WORKERS:
        frappe.throw(
            _("A manifest can list at most {0} expected workers.").format(_MAX_EXPECTED_WORKERS)
        )

    # [#armp03] copy only the allowlisted child fields - never "temporary_worker".
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
    # Request-boundary auto-commit persists this on success; a manual commit here would
    # defeat the framework rollback if a later write is ever added. [[reference-frappe-commit-in-request-antipattern]]
    return {"name": doc.name}
