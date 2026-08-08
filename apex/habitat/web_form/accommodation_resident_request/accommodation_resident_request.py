# Copyright (c) 2026, afmcoltd
import frappe
from frappe import _

from apex.apex_core.utils.rate_limit_identity import rate_limit


def get_context(context):
    """Disables caching on the resident request web form so every visit renders fresh."""
    context.no_cache = 1


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=5, seconds=60)
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
    if website_field:
        return {"name": None, "tracking_code": None}

    if len(description or "") > 2000:
        frappe.throw(_("Description is too long. Please keep it under 2000 characters."))

    doc = frappe.get_doc({
        "doctype": "Resident Request",
        "location_token": location_token,
        "request_category": request_type,
        "description": description,
        "mobile_number": contact_number,
        "source_channel": "QR Web Form",
    })
    doc.insert(ignore_permissions=True)
    return {"name": doc.name, "tracking_code": doc.anonymous_tracking_code}
