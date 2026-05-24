import frappe
from frappe import _


def get_context(context):
    context.no_cache = 1


@frappe.whitelist(allow_guest=True, methods=["POST"])
@frappe.rate_limit(key="frappe.request.remote_addr", limit=5, seconds=60)
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
    # Fix 3b: honeypot — silently succeed but discard bot submissions
    if website_field:
        return {"name": None, "tracking_code": None}

    # Fix 3d: server-side length cap on description
    if len(description or "") > 2000:
        frappe.throw(_("Description is too long. Please keep it under 2000 characters."))

    # Fix 3a: map public param names to the correct DocType fieldnames
    doc = frappe.get_doc({
        "doctype": "Accommodation Resident Request",
        "location_token": location_token,
        "request_category": request_type,   # was incorrectly keyed as request_type
        "description": description,
        "mobile_number": contact_number,    # was incorrectly keyed as contact_number
        "source_channel": "QR Web Form",
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return {"name": doc.name, "tracking_code": doc.anonymous_tracking_code}
