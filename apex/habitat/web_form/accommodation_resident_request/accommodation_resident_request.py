# Copyright (c) 2026, AFMCO and contributors
import frappe
from frappe import _
from frappe.rate_limiter import rate_limit


def get_context(context):
    context.no_cache = 1


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(key="frappe.request.remote_addr", limit=5, seconds=60)
def submit_resident_request(
    location_token,
    request_type,
    description,
    contact_number=None,
    website_field=None,
):
    """Rate-limited public endpoint for resident request submission.

    Replaces direct Web Form submit for programmatic callers.
    Limit: 5 requests per IP per 60 seconds.

    Parameter notes:
    - ``request_type`` maps to the DocType field ``request_category``.
    - ``contact_number`` maps to the DocType field ``mobile_number``.
      The public parameter names are kept for backward compatibility with
      existing QR forms and external callers.
    - ``website_field`` is a honeypot; any non-empty value is rejected.
    """
    # [#q0bt8w]
    if website_field:
        return {"name": None, "tracking_code": None}

    # [#oskg6d]
    if len(description or "") > 2000:
        frappe.throw(_("Description is too long. Please keep it under 2000 characters."))

    # [#nxrqsg]
    doc = frappe.get_doc({
        "doctype": "Resident Request",
        "location_token": location_token,
        "request_category": request_type,   # [#nnkung]
        "description": description,
        "mobile_number": contact_number,    # [#kitufc]
        "source_channel": "QR Web Form",
    })
    doc.insert(ignore_permissions=True)  # audit-ok — guest QR web-form intake, rate-limited + honeypot-guarded
    frappe.db.commit()
    return {"name": doc.name, "tracking_code": doc.anonymous_tracking_code}
